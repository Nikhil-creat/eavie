from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-secret-change-me-please-32bytes"
    ACCESS_MIN: int = 15
    REFRESH_DAYS: int = 7
    DATABASE_URL: str = "postgresql+asyncpg://eavie:eavie@postgres:5432/eavie"
    REDIS_URL: str = "redis://redis:6379/0"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    QDRANT_URL: str = ":memory:"
    EMBED_MODEL: str = "BAAI/bge-small-en-v1.5"
    RERANK_MODEL: str = "BAAI/bge-reranker-base"
    CNN_WEIGHTS_PATH: str = "/models/defect_cnn.pt"
    EVAL_THRESHOLD: float = 0.35
    RATE_CAPACITY: int = 30
    RATE_LEAK_PER_SEC: float = 0.5
    OTLP_ENDPOINT: str = ""
settings = Settings()
