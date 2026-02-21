from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.unlock import issue_unlock_token, UnlockError

router = APIRouter(prefix="/api/unlock", tags=["unlock"])


class IssueUnlockRequest(BaseModel):
    device_id: str
    method: str


class IssueUnlockResponse(BaseModel):
    unlock_token: str
    expires_in: int


@router.post("/issue", response_model=IssueUnlockResponse)
async def issue_unlock(req: IssueUnlockRequest, db: AsyncSession = Depends(get_db)):
    try:
        token = await issue_unlock_token(
            db=db,
            device_id=req.device_id.strip(),
            method=req.method.strip(),
        )
    except UnlockError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error_code": e.error_code, "message": e.message},
        )
    return IssueUnlockResponse(unlock_token=token, expires_in=600)
