"""
MySQL 数据库连接池和表初始化
使用 SQLAlchemy + aiomysql 实现异步连接池
"""
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text, Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.sql import func

from backend.config.settings import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class KnowledgeItem(Base):
    """知识库条目表 - 存储ChromaDB元数据镜像"""
    __tablename__ = "knowledge_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_name = Column(String(128), nullable=False, default="default")
    content = Column(Text, nullable=False)
    filename = Column(String(512), nullable=True)
    chroma_id = Column(String(128), nullable=True, comment="ChromaDB 中的文档 ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# 异步引擎
async_engine = create_async_engine(
    settings.mysql_url,
    pool_size=settings.MYSQL_POOL_SIZE,
    max_overflow=settings.MYSQL_POOL_OVERFLOW,
    pool_timeout=settings.MYSQL_POOL_TIMEOUT,
    pool_recycle=3600,
    echo=False,
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_database() -> None:
    """初始化数据库，创建所有表"""
    async with async_engine.begin() as conn:
        logger.info("Creating database tables if not exist...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized.")


async def close_database() -> None:
    """关闭数据库连接池"""
    await async_engine.dispose()
    logger.info("Database connection pool closed.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（用于依赖注入）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncSession:
    """直接获取数据库会话"""
    return AsyncSessionLocal()


# 同步引擎（用于 Alembic 迁移等场景）
from sqlalchemy import create_engine

sync_engine = create_engine(
    settings.mysql_sync_url,
    pool_size=settings.MYSQL_POOL_SIZE,
    max_overflow=settings.MYSQL_POOL_OVERFLOW,
    pool_recycle=3600,
    echo=False,
)
