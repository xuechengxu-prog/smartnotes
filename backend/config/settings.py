"""
统一配置模块
所有环境变量和全局配置集中管理
"""
import os
from typing import Optional


class Settings:
    """应用配置类"""

    # LLM 配置（百炼 qwen3.7-plus）
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3.7-plus")
    LLM_BASE_URL: str = os.getenv(
        "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))

    # MySQL 配置
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "smartnotes")
    MYSQL_POOL_SIZE: int = int(os.getenv("MYSQL_POOL_SIZE", "10"))
    MYSQL_POOL_OVERFLOW: int = int(os.getenv("MYSQL_POOL_OVERFLOW", "20"))
    MYSQL_POOL_TIMEOUT: int = int(os.getenv("MYSQL_POOL_TIMEOUT", "30"))

    # Redis 配置
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD") or None
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_POOL_SIZE: int = int(os.getenv("REDIS_POOL_SIZE", "50"))

    # JWT 配置
    JWT_SECRET: str = os.getenv("JWT_SECRET", "smartnotes-secret-key-change-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    # 限流配置
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # 秒
    RATE_LIMIT_MAX_REQUESTS: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))

    # 缓存配置
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "3600"))  # 秒
    SESSION_TTL: int = int(os.getenv("SESSION_TTL", "86400"))  # 秒

    # ChromaDB 配置
    CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))

    # 服务地址配置
    AGENT_NOTE_HOST: str = os.getenv("AGENT_NOTE_HOST", "agent_note")
    AGENT_NOTE_PORT: int = int(os.getenv("AGENT_NOTE_PORT", "8001"))
    AGENT_PLAN_HOST: str = os.getenv("AGENT_PLAN_HOST", "agent_plan")
    AGENT_PLAN_PORT: int = int(os.getenv("AGENT_PLAN_PORT", "8002"))
    AGENT_QA_HOST: str = os.getenv("AGENT_QA_HOST", "agent_qa")
    AGENT_QA_PORT: int = int(os.getenv("AGENT_QA_PORT", "8003"))
    GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))

    @classmethod
    def validate(cls) -> None:
        """验证必要配置"""
        if not cls.DASHSCOPE_API_KEY:
            raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")
        if not cls.MYSQL_PASSWORD:
            raise ValueError("MYSQL_PASSWORD 环境变量未设置")

    @property
    def mysql_url(self) -> str:
        """MySQL 连接 URL"""
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    @property
    def mysql_sync_url(self) -> str:
        """MySQL 同步连接 URL"""
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )


# 全局配置实例
settings = Settings()
