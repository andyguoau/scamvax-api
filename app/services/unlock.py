import base64
import hashlib
import hmac
import json
import time
import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.models.unlock import DeviceWallet, UnlockTokenUse

settings = get_settings()
_TOKEN_TTL_SECONDS = 10 * 60
_METHODS = {"CREDIT", "BONUS"}


class UnlockError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 402):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _sign(payload_part: str) -> str:
    secret = settings.secret_key.encode("utf-8")
    digest = hmac.new(secret, payload_part.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)


async def _ensure_wallet(db: AsyncSession, device_id: str) -> DeviceWallet:
    # Postgres: 并发安全地初始化默认钱包
    await db.execute(
        text(
            """
            INSERT INTO device_wallets (device_id, credits, bonus_used)
            VALUES (:device_id, 100, false)
            ON CONFLICT (device_id) DO NOTHING
            """
        ),
        {"device_id": device_id},
    )
    result = await db.execute(
        select(DeviceWallet).where(DeviceWallet.device_id == device_id)
    )
    wallet = result.scalars().first()
    if wallet is None:
        raise UnlockError("WALLET_UNAVAILABLE", "钱包初始化失败", status_code=503)
    return wallet


async def issue_unlock_token(db: AsyncSession, device_id: str, method: str) -> str:
    method = method.strip().upper()
    if method not in _METHODS:
        raise UnlockError("INVALID_UNLOCK_METHOD", "不支持的解锁方式", status_code=400)

    wallet = await _ensure_wallet(db, device_id)
    if method == "CREDIT" and wallet.credits <= 0:
        raise UnlockError("UNLOCK_REQUIRED", "可用次数不足")
    if method == "BONUS" and wallet.bonus_used:
        raise UnlockError("UNLOCK_REQUIRED", "奖励次数已用完")

    payload = {
        "v": 1,
        "jti": uuid.uuid4().hex,
        "did": device_id,
        "m": method,
        "exp": int(time.time()) + _TOKEN_TTL_SECONDS,
    }
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig_part = _sign(payload_part)
    return f"{payload_part}.{sig_part}"


def _verify_and_parse(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 2:
        raise UnlockError("INVALID_UNLOCK_TOKEN", "解锁令牌格式错误")
    payload_part, sig_part = parts
    if not hmac.compare_digest(_sign(payload_part), sig_part):
        raise UnlockError("INVALID_UNLOCK_TOKEN", "解锁令牌签名无效")
    try:
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    except Exception:
        raise UnlockError("INVALID_UNLOCK_TOKEN", "解锁令牌解析失败")
    if not isinstance(payload, dict):
        raise UnlockError("INVALID_UNLOCK_TOKEN", "解锁令牌无效")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise UnlockError("UNLOCK_TOKEN_EXPIRED", "解锁令牌已过期")
    return payload


async def consume_unlock_token(db: AsyncSession, device_id: str, token: str) -> str:
    payload = _verify_and_parse(token)
    token_device = payload.get("did")
    method = str(payload.get("m", "")).upper()
    jti = str(payload.get("jti", ""))

    if token_device != device_id:
        raise UnlockError("INVALID_UNLOCK_TOKEN", "解锁令牌与设备不匹配")
    if method not in _METHODS or not jti:
        raise UnlockError("INVALID_UNLOCK_TOKEN", "解锁令牌字段无效")

    used = await db.get(UnlockTokenUse, jti)
    if used is not None:
        raise UnlockError("UNLOCK_TOKEN_USED", "解锁令牌已被使用")

    # 行级锁，保证扣减原子性
    await db.execute(
        text(
            """
            INSERT INTO device_wallets (device_id, credits, bonus_used)
            VALUES (:device_id, 100, false)
            ON CONFLICT (device_id) DO NOTHING
            """
        ),
        {"device_id": device_id},
    )
    result = await db.execute(
        select(DeviceWallet)
        .where(DeviceWallet.device_id == device_id)
        .with_for_update()
    )
    wallet = result.scalars().first()
    if wallet is None:
        raise UnlockError("WALLET_UNAVAILABLE", "钱包读取失败", status_code=503)

    if method == "CREDIT":
        if wallet.credits <= 0:
            raise UnlockError("UNLOCK_REQUIRED", "可用次数不足")
        wallet.credits -= 1
    elif method == "BONUS":
        if wallet.bonus_used:
            raise UnlockError("UNLOCK_REQUIRED", "奖励次数已用完")
        wallet.bonus_used = True

    db.add(UnlockTokenUse(jti=jti, device_id=device_id, method=method))
    return method
