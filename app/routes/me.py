from fastapi import APIRouter, Depends

from app.core.security import require_user

router = APIRouter(tags=["auth"])


@router.get("/me")
async def get_me(user=Depends(require_user)):
    return {
        "uid": user.get("uid"),
        "email": user.get("email"),
        "phone_number": user.get("phone_number"),
        "name": user.get("name"),
    }
