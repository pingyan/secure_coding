from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./aims.db"
    JWT_SECRET_KEY: str = "change-me-in-production-use-a-random-256-bit-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 30
    API_KEY_PREFIX: str = "aims_"
    KEY_ROTATION_GRACE_HOURS: int = 24
    RATE_LIMIT_AUTH_PER_MINUTE: int = 20
    RATE_LIMIT_API_PER_MINUTE: int = 60

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
