from fastapi import APIRouter, HTTPException, status as httpStatus

from app.core.constants import placesCollectionName
from app.core.firebase import firebaseProjectId, firestoreDb


router = APIRouter()


@router.get("/health")
def health():
    try:
        firestoreDb.collection(placesCollectionName).limit(1).get()
    except Exception as error:
        raise HTTPException(
            status_code=httpStatus.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore is unavailable",
        ) from error

    return {
        "ok": True,
        "firebaseProjectId": firebaseProjectId,
        "firestoreDatabaseId": "(default)",
    }
