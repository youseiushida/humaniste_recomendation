from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_NORMALIZE_MODEL: str = "gpt-5"
    OPENAI_EMBED_MODEL: str = "text-embedding-3-large"

    # microCMS
    MICROCMS_API_KEY: str
    MICROCMS_SERVICE_ID: str
    MICROCMS_WEBHOOK_SECRET: str | None = None
    MICROCMS_ENDPOINT: str = "blog"
    MICROCMS_RELATION_FIELD: str = "related_blog_post"

    # Database
    DATABASE_URL: str = "postgresql+psycopg://app:app@localhost:9002/app"


settings = Settings()  # type: ignore[misc]


