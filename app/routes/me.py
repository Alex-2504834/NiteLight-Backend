from fastapi import APIRouter, Depends

from app.core.security import require_user

router = APIRouter()


@router.get("/me")
def get_me(user=Depends(require_user)):
    return user
