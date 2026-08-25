from fastapi import APIRouter, Depends

from app.core.security import requireUser


router = APIRouter()


@router.get("/me")
def getMe(user=Depends(requireUser)):
    return user
