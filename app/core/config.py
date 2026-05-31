import os


class Settings:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.port = int(os.getenv("PORT", "8000"))
        self.host = os.getenv("HOST", "0.0.0.0")
        self.firebase_service_account_json = os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_JSON",
            "",
        )
        self.allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
        self.stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "")
        self.stripe_currency = os.getenv("STRIPE_CURRENCY", "gbp")
        self.stripe_test_amount = int(os.getenv("STRIPE_TEST_AMOUNT", "100"))

    @property
    def allowed_origins_list(self) -> list[str]:
        if not self.allowed_origins:
            return ["*"]

        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
