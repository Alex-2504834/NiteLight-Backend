from fastapi import APIRouter, Depends

from app.core.security import requireAdmin


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
def adminPing(user=Depends(requireAdmin)):
    return {
        "ok": True,
        "uid": user["uid"],
    }
