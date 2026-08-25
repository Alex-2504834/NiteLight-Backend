from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, status as httpStatus

from app.core.config import settings
from app.core.security import requireUser


router = APIRouter(prefix="/payments", tags=["payments"])
paymentPurpose = "mobile_test_payment"


@router.post("/test-payment-sheet")
def createTestPaymentSheet(user: dict[str, Any] = Depends(requireUser)):
    if not settings.stripeSecretKey:
        raise HTTPException(
            status_code=httpStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe secret key is not configured",
        )

    stripe.api_key = settings.stripeSecretKey

    try:
        paymentIntent = stripe.PaymentIntent.create(
            amount=settings.stripeTestAmount,
            currency=settings.stripeCurrency,
            automatic_payment_methods={"enabled": True},
            metadata={
                "firebaseUid": user["uid"] or "",
                "purpose": paymentPurpose,
            },
        )
    except Exception as error:
        raise HTTPException(
            status_code=httpStatus.HTTP_502_BAD_GATEWAY,
            detail="Unable to create Stripe payment intent",
        ) from error

    return {
        "paymentIntentClientSecret": paymentIntent.client_secret,
        "amount": settings.stripeTestAmount,
        "currency": settings.stripeCurrency,
    }
