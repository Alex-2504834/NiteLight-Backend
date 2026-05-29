from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.firebase import firestore_db
from app.core.security import require_user

router = APIRouter(prefix="/places", tags=["places"])


def server_timestamp():
    from google.cloud import firestore as google_firestore

    return google_firestore.SERVER_TIMESTAMP


@router.get("")
def list_places():
    docs = firestore_db.collection("places").stream()

    places: list[dict[str, Any]] = []

    for doc in docs:
        data = doc.to_dict() or {}
        data["id"] = doc.id
        places.append(data)

    return {"places": places}


@router.get("/{place_id}")
def get_place(place_id: str):
    doc = firestore_db.collection("places").document(place_id).get()

    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")

    data = doc.to_dict() or {}
    data["id"] = doc.id

    return data


@router.post("")
def create_or_update_place(place: dict[str, Any], user=Depends(require_user)):
    place_id = place.get("id")

    if place_id:
        doc_ref = firestore_db.collection("places").document(str(place_id))
    else:
        doc_ref = firestore_db.collection("places").document()

    data = {**place}
    data.pop("id", None)
    data["updatedAt"] = server_timestamp()
    data["updatedBy"] = user["uid"]

    if not doc_ref.get().exists:
        data["createdAt"] = server_timestamp()
        data["createdBy"] = user["uid"]

    doc_ref.set(data, merge=True)

    return {"id": doc_ref.id, **data}


@router.patch("/{place_id}")
def update_place(place_id: str, updates: dict[str, Any], user=Depends(require_user)):
    doc_ref = firestore_db.collection("places").document(place_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")

    updates = {**updates, "updatedBy": user["uid"], "updatedAt": server_timestamp()}
    doc_ref.update(updates)

    updated_doc = doc_ref.get()
    data = updated_doc.to_dict() or {}
    data["id"] = updated_doc.id

    return data


@router.delete("/{place_id}")
def delete_place(place_id: str, user=Depends(require_user)):
    doc_ref = firestore_db.collection("places").document(place_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")

    doc_ref.delete()

    return {"deleted": True, "id": place_id}
