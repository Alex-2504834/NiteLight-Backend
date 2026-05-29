from fastapi import APIRouter, Depends

from app.core.security import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
async def admin_ping(user=Depends(require_admin)):
    return {
        "ok": True,
        "message": "Admin access confirmed",
        "uid": user.get("uid"),
    }
