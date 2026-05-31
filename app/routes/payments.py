from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import require_user


router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/test-payment-sheet")
def create_test_payment_sheet(user: dict[str, Any] = Depends(require_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe secret key is not configured",
        )

    stripe.api_key = settings.stripe_secret_key

    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=settings.stripe_test_amount,
            currency=settings.stripe_currency,
            automatic_payment_methods={"enabled": True},
            metadata={
                "firebaseUid": user["uid"] or "",
                "purpose": "mobile_test_payment",
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to create Stripe payment intent",
        ) from exc

    return {
        "paymentIntentClientSecret": payment_intent.client_secret,
        "amount": settings.stripe_test_amount,
        "currency": settings.stripe_currency,
    }
