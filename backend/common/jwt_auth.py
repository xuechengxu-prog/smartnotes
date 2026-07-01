"""
JWT 认证工具
提供 Token 的创建、验证和解码功能
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import jwt
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config.settings import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class JWTAuth:
    """JWT 认证工具类"""

    @staticmethod
    def create_token(
        user_id: int,
        username: str,
        extra_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        创建 JWT Token
        :param user_id: 用户 ID
        :param username: 用户名
        :param extra_claims: 额外声明
        :return: JWT Token 字符串
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "username": username,
            "iat": now,
            "exp": now + timedelta(hours=settings.JWT_EXPIRE_HOURS),
            "type": "access",
        }
        if extra_claims:
            payload.update(extra_claims)

        token = jwt.encode(
            payload,
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )
        return token

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """
        解码并验证 JWT Token
        :param token: JWT Token 字符串
        :return: Token 载荷
        :raises HTTPException: Token 无效或过期
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            raise HTTPException(status_code=401, detail="Token 已过期")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise HTTPException(status_code=401, detail="无效的 Token")

    @staticmethod
    def get_user_id_from_token(token: str) -> int:
        """从 Token 中提取用户 ID"""
        payload = JWTAuth.decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token 中未找到用户 ID")
        return int(user_id)

    @staticmethod
    async def get_current_user(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = None,
    ) -> Dict[str, Any]:
        """
        获取当前用户（用于 FastAPI 依赖注入）
        优先从 Header 获取，其次从 Cookie 获取
        """
        token = None

        # 从 Authorization Header 获取
        if credentials:
            token = credentials.credentials
        else:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]

        # 从 Cookie 获取
        if not token:
            token = request.cookies.get("access_token")

        if not token:
            raise HTTPException(status_code=401, detail="未提供认证信息")

        payload = JWTAuth.decode_token(token)
        return {
            "user_id": int(payload.get("sub", 0)),
            "username": payload.get("username", ""),
        }


def get_current_user_dependency(
    credentials: Optional[HTTPAuthorizationCredentials] = None,
) -> Any:
    """
    FastAPI 依赖注入函数
    用法: user = Depends(get_current_user_dependency)
    """
    from fastapi import Depends

    async def _get_user(
        request: Request,
        creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
    ) -> Dict[str, Any]:
        return await JWTAuth.get_current_user(request, creds or credentials)

    return _get_user
