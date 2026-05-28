from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "AR Reconciliation Engine"

    # Database: set DB_TYPE to "postgresql" and provide POSTGRES_* vars to use PostgreSQL
    DB_TYPE: str = "sqlite"  # "sqlite" or "postgresql"
    DATABASE_URL: str = "sqlite:///./data/ar_reconciliation.db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "ar_reconciliation"

    FAILURE_RATE: float = 0.20  # 20% random failure
    MAX_RETRIES: int = 3
    MATCH_TOLERANCE_PERCENT: float = (
        5.0  # % difference allowed to still count as MATCHED
    )
    HIGH_VALUE_THRESHOLD: float = (
        10000.0  # invoices above this are flagged as high-value
    )
    STALE_MINUTES: int = 10  # failed workflows older than this are considered stale

    @property
    def effective_database_url(self) -> str:
        if self.DB_TYPE == "postgresql":
            return (
                f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return self.DATABASE_URL

    class Config:
        env_file = ".env"


settings = Settings()
