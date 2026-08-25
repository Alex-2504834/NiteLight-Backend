import os


def getIntEnvironmentValue(name: str, defaultValue: int) -> int:
    return int(os.getenv(name, str(defaultValue)))



class Settings:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.port = getIntEnvironmentValue("PORT", 8000)
        self.host = os.getenv("HOST", "0.0.0.0")
        self.firebaseServiceAccountJson = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        self.allowedOrigins = os.getenv("ALLOWED_ORIGINS", "*")
        self.stripeSecretKey = os.getenv("STRIPE_SECRET_KEY", "")
        self.stripeCurrency = os.getenv("STRIPE_CURRENCY", "gbp")
        self.stripeTestAmount = getIntEnvironmentValue("STRIPE_TEST_AMOUNT", 100)
        self.googlePlacesApiKey = os.getenv("GOOGLE_PLACES_API_KEY", "")
        self.adminApiKey = os.getenv("ADMIN_API_KEY", "")

    @property
    def allowedOriginsList(self) -> list[str]:
        if not self.allowedOrigins:
            return ["*"]

        return [
            origin.strip()
            for origin in self.allowedOrigins.split(",")
            if origin.strip()
        ]


settings = Settings()
