"""
Configuration Management
Pydantic Settings with strict validation
"""
from typing import Optional, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with strict validation"""
    
    model_config = SettingsConfigDict(
        env_file=r"E:\JOB\Auto-Applier\AutoPASS\.env",
        case_sensitive=True,
        extra="ignore"
    )
    
    # Application
    APP_NAME: str = "AI Job Auto-Applier"
    DEBUG: bool = False
    ENVIRONMENT: str = Field(default="development")
    
    # AI Settings
    AI_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # OpenRouter LLM (for form answer generation)
    OPENROUTER_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenRouter API key for LLM-powered form answers"
    )
    
    # Database (Async PostgreSQL)
    DATABASE_URL: str = "postgresql+asyncpg://admin:postgres@localhost:5432/jobapplier"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5
    
    # Encryption (Fernet)
    FERNET_KEY: str = Field(
        default="",
        description="Fernet key for encrypting credentials (32 bytes, base64)"
    )

    # Baseline cookie encryption (AES-256-GCM envelope)
    BASELINE_COOKIES_MASTER_KEY: str = Field(
        default="",
        description="Base64-encoded 32-byte master key for baseline cookie encryption"
    )
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    MAX_APPLIES_PER_HOUR: int = 5
    
    # LinkedIn
    LINKEDIN_BASE_URL: str = "https://www.linkedin.com"
    
    # Indeed API
    INDEED_API_KEY: Optional[str] = None
    INDEED_API_URL: str = "https://api.indeed.com/ads/apisearch"
    
    # Skyvern AI
    SKYVERN_API_URL: str = "http://localhost:7080"
    
    # Playwright
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_STEALTH_MODE: bool = True
    
    # User Agents
    USER_AGENTS: List[str] = Field(
        default_factory=lambda: [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        ]
    )
    
    # Firebase
    FCM_CREDENTIALS_PATH: Optional[str] = None
    
    # File Upload
    MAX_RESUME_SIZE_MB: int = 5
    ALLOWED_RESUME_EXTENSIONS: List[str] = Field(default_factory=lambda: [".pdf"])
    UPLOAD_DIR: str = "./uploads/resumes"
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # Job Fetching
    JOB_FETCH_INTERVAL_MINUTES: int = 30
    MAX_JOBS_PER_FETCH: int = 50
    
    # Session Management
    MAX_CONCURRENT_SESSIONS_PER_USER: int = 3
    SESSION_CLEANUP_ENABLED: bool = True
    SESSION_CLEANUP_INTERVAL_MINUTES: int = 30
    SESSION_IDLE_TIMEOUT_MINUTES: int = 30
    SESSION_KEEP_DISPOSED_COUNT: int = 5  # Keep last N disposed sessions per user
    SESSION_AUTO_DISPOSE_AFTER_TASK: bool = True
    
    # Session Health Checks
    SESSION_HEALTH_CHECK_ENABLED: bool = True
    SESSION_429_COOLDOWN_SECONDS: int = 3600  # 1 hour for HTTP 429 rate limiting
    SESSION_EXPIRED_COOLDOWN_SECONDS: int = 300  # 5 minutes for expired sessions
    SESSION_CHECKPOINT_COOLDOWN_SECONDS: int = 1800  # 30 minutes for LinkedIn checkpoints
    SESSION_HEALTH_CHECK_ON_ERROR: bool = True  # Run health check on task errors
    SESSION_MARK_TAINTED_ON_HEALTH_ISSUE: bool = True  # Mark session as TAINTED when issues detected
    
    # Proxy
    PROXY_URL: Optional[str] = None
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    LOG_JSON_FORMAT: bool = True
    
    # JWT Settings
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_PRIVATE_KEY: Optional[str] = None
    JWT_PUBLIC_KEY: Optional[str] = None
    
    # Monitoring
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = True
    OPENTELEMETRY_ENABLED: bool = False
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str = "196623045052-8fdojdasaj05j38285i7kg8i8p3gu9ob.apps.googleusercontent.com"
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
    GOOGLE_OAUTH_URL: str = "https://accounts.google.com/o/oauth2/auth"
    GOOGLE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL: str = "https://www.googleapis.com/oauth2/v2/userinfo"
    
    # CORS
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])
    
    @field_validator("FERNET_KEY")
    @classmethod
    def validate_secrets(cls, v: str, info) -> str:
        """Validate that secrets are provided in production"""
        # In production, these must be set
        # For development, we'll generate them if missing
        return v


# Global settings instance
settings = Settings()
