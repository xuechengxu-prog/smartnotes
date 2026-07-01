"""
Redis 客户端封装
提供限流、缓存、Session 管理等功能
"""
import json
import logging
import time
from typing import Optional, Any, Union
from urllib.parse import urlparse

import redis.asyncio as redis

from backend.config.settings import settings

logger = logging.getLogger(__name__)


def _parse_redis_url(url: str) -> dict:
    """解析 REDIS_URL，提取连接参数"""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 6379,
        "password": parsed.password or None,
        "db": int(parsed.path.lstrip("/")) if parsed.path else 0,
    }


class RedisClient:
    """Redis 客户端封装类"""

    _instance: Optional["RedisClient"] = None
    _pool: Optional[redis.Redis] = None

    def __new__(cls) -> "RedisClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self) -> None:
        """建立 Redis 连接"""
        if self._pool is None:
            # 优先使用 REDIS_URL，否则使用单独的配置项
            if settings.REDIS_URL:
                params = _parse_redis_url(settings.REDIS_URL)
                host = params["host"]
                port = params["port"]
                password = params["password"]
                db = params["db"]
            else:
                host = settings.REDIS_HOST
                port = settings.REDIS_PORT
                password = settings.REDIS_PASSWORD
                db = settings.REDIS_DB

            self._pool = redis.Redis(
                host=host,
                port=port,
                password=password,
                db=db,
                max_connections=settings.REDIS_POOL_SIZE,
                decode_responses=True,
            )
            logger.info(f"Redis client connected to {host}:{port} db={db}")
            # 测试连接
            try:
                await self._pool.ping()
            except Exception as e:
                logger.error(f"Redis connection test failed: {e}")
                self._pool = None
                raise

    async def close(self) -> None:
        """关闭 Redis 连接"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Redis client closed.")

    @property
    def client(self) -> redis.Redis:
        """获取 Redis 客户端实例，如果未连接则返回 None（调用方需处理）"""
        return self._pool

    # ==================== 限流功能（滑动窗口）====================

    async def is_rate_limited(
        self,
        key: str,
        window: int = settings.RATE_LIMIT_WINDOW,
        max_requests: int = settings.RATE_LIMIT_MAX_REQUESTS,
    ) -> bool:
        """
        滑动窗口限流检查
        :param key: 限流键（如 user_id 或 IP）
        :param window: 窗口大小（秒）
        :param max_requests: 窗口内最大请求数
        :return: True 表示被限流，False 表示未限流
        """
        now = time.time()
        window_start = now - window
        redis_key = f"rate_limit:{key}"

        pipe = self.client.pipeline()
        # 移除窗口外的旧记录
        pipe.zremrangebyscore(redis_key, 0, window_start)
        # 添加当前请求
        pipe.zadd(redis_key, {str(now): now})
        # 统计窗口内请求数
        pipe.zcard(redis_key)
        # 设置 key 过期时间
        pipe.expire(redis_key, window + 1)

        results = await pipe.execute()
        current_count = results[2]

        if current_count > max_requests:
            # 如果超限，移除刚刚添加的记录
            await self.client.zrem(redis_key, str(now))
            logger.warning(f"Rate limit exceeded for key: {key}")
            return True
        return False

    async def get_rate_limit_info(
        self, key: str, window: int = settings.RATE_LIMIT_WINDOW
    ) -> dict:
        """获取限流信息"""
        now = time.time()
        window_start = now - window
        redis_key = f"rate_limit:{key}"

        count = await self.client.zcount(redis_key, window_start, now)
        ttl = await self.client.ttl(redis_key)

        return {
            "current_requests": count,
            "max_requests": settings.RATE_LIMIT_MAX_REQUESTS,
            "window": window,
            "ttl": ttl,
        }

    # ==================== 缓存功能 ====================

    async def cache_get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        value = await self.client.get(f"cache:{key}")
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    async def cache_set(
        self,
        key: str,
        value: Any,
        ttl: int = settings.CACHE_TTL,
    ) -> None:
        """设置缓存"""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        await self.client.setex(f"cache:{key}", ttl, value)

    async def cache_delete(self, key: str) -> None:
        """删除缓存"""
        await self.client.delete(f"cache:{key}")

    async def cache_exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        return await self.client.exists(f"cache:{key}") > 0

    # ==================== Session 功能 ====================

    async def session_get(self, session_id: str) -> Optional[dict]:
        """获取 Session"""
        value = await self.client.get(f"session:{session_id}")
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def session_set(
        self,
        session_id: str,
        data: dict,
        ttl: int = settings.SESSION_TTL,
    ) -> None:
        """设置 Session"""
        await self.client.setex(
            f"session:{session_id}", ttl, json.dumps(data, ensure_ascii=False)
        )

    async def session_delete(self, session_id: str) -> None:
        """删除 Session"""
        await self.client.delete(f"session:{session_id}")

    async def session_refresh(self, session_id: str, ttl: int = settings.SESSION_TTL) -> None:
        """刷新 Session 过期时间"""
        await self.client.expire(f"session:{session_id}", ttl)

    # ==================== 通用工具 ====================

    async def ping(self) -> bool:
        """检查 Redis 连接是否正常"""
        try:
            return await self.client.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False


# 全局 Redis 客户端实例
redis_client = RedisClient()
