"""
统一网关服务
提供 JWT 认证、Redis 限流、路由转发到各 Agent
"""
import logging
from contextlib import asynccontextmanager

import bcrypt
import httpx
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.common.jwt_auth import JWTAuth
from backend.common.redis_client import redis_client
from backend.common.database import init_database, close_database, get_db_session, User
from backend.config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HTTP 客户端
http_client = httpx.AsyncClient(timeout=60.0)


# Pydantic 模型
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="用户名")
    email: str = Field("", description="邮箱")
    password: str = Field(..., min_length=6, description="密码")


class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class AuthResponse(BaseModel):
    token: str = Field(..., description="JWT Token")
    user_id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")


class ProxyRequest(BaseModel):
    method: str = Field("POST", description="HTTP 方法")
    path: str = Field(..., description="目标路径")
    body: dict = Field(default_factory=dict, description="请求体")
    headers: dict = Field(default_factory=dict, description="额外请求头")


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Gateway starting up...")
    settings.validate()
    await redis_client.connect()
    await init_database()
    logger.info("Gateway started.")
    yield
    logger.info("Gateway shutting down...")
    await close_database()
    await redis_client.close()
    await http_client.aclose()
    logger.info("Gateway stopped.")


app = FastAPI(
    title="SmartNotes - Gateway",
    description="统一网关服务",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 认证相关 ====================

def _hash_password(password: str) -> str:
    """使用 bcrypt 加密密码"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


@app.post("/api/auth/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """
    用户注册
    查询 MySQL 数据库，bcrypt 加密存储密码
    """
    session = await get_db_session()
    try:
        # 检查用户名是否已存在
        result = await session.execute(
            select(User).where(User.username == request.username)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="用户名已存在")

        # 检查邮箱是否已存在（仅当提供了邮箱时）
        if request.email:
            result = await session.execute(
                select(User).where(User.email == request.email)
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="邮箱已存在")

        # 创建用户
        password_hash = _hash_password(request.password)
        user = User(
            username=request.username,
            email=request.email if request.email else None,
            password_hash=password_hash,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # 生成 JWT Token
        token = JWTAuth.create_token(user_id=user.id, username=user.username)

        logger.info(f"User registered: {request.username}")
        return AuthResponse(
            token=token,
            user_id=user.id,
            username=user.username,
        )
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Register failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")
    finally:
        await session.close()


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    用户登录
    查询 MySQL 数据库验证用户，bcrypt 验证密码
    """
    session = await get_db_session()
    try:
        result = await session.execute(
            select(User).where(User.username == request.username)
        )
        user = result.scalar_one_or_none()

        if not user or not _verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 生成 JWT Token
        token = JWTAuth.create_token(user_id=user.id, username=user.username)

        logger.info(f"User logged in: {request.username}")
        return AuthResponse(
            token=token,
            user_id=user.id,
            username=user.username,
        )
    finally:
        await session.close()


@app.get("/api/auth/me")
async def get_me(request: Request):
    """获取当前用户信息"""
    user = await JWTAuth.get_current_user(request)
    return {
        "user_id": user["user_id"],
        "username": user["username"],
    }


# ==================== 限流中间件 ====================

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """
    Redis 滑动窗口限流中间件
    对 /api/ 路径进行限流
    """
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    # 获取限流 key（优先用户 ID，其次 IP）
    rate_key = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header[7:]
            user_id = JWTAuth.get_user_id_from_token(token)
            rate_key = f"user:{user_id}"
        except Exception:
            pass

    if not rate_key:
        rate_key = f"ip:{request.client.host}"

    # 检查限流（Redis 可能尚未连接，跳过限流）
    client = redis_client.client
    if client is None:
        return await call_next(request)

    is_limited = await redis_client.is_rate_limited(
        key=rate_key,
        window=settings.RATE_LIMIT_WINDOW,
        max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    )

    if is_limited:
        limit_info = await redis_client.get_rate_limit_info(rate_key)
        return JSONResponse(
            status_code=429,
            content={
                "detail": "请求过于频繁，请稍后再试",
                "limit_info": limit_info,
            },
        )

    response = await call_next(request)
    return response


# ==================== 路由转发 ====================

async def _proxy_request(
    service_host: str,
    service_port: int,
    path: str,
    method: str,
    body: dict = None,
    headers: dict = None,
    user_id: int = None,
) -> httpx.Response:
    """转发请求到下游服务（非流式）"""
    url = f"http://{service_host}:{service_port}{path}"
    proxy_headers = {}
    if headers:
        proxy_headers.update(headers)
    if user_id:
        proxy_headers["X-User-Id"] = str(user_id)

    try:
        if method.upper() == "GET":
            response = await http_client.get(url, headers=proxy_headers, params=body)
        elif method.upper() == "POST":
            response = await http_client.post(url, json=body, headers=proxy_headers)
        elif method.upper() == "DELETE":
            response = await http_client.delete(url, headers=proxy_headers)
        else:
            response = await http_client.request(method.upper(), url, json=body, headers=proxy_headers)
        return response
    except httpx.RequestError as e:
        logger.error(f"Proxy request failed: {e}")
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")


async def _proxy_stream_request(
    service_host: str,
    service_port: int,
    path: str,
    body: dict = None,
    headers: dict = None,
    user_id: int = None,
):
    """流式转发请求到下游服务"""
    url = f"http://{service_host}:{service_port}{path}"
    proxy_headers = {"Content-Type": "application/json"}
    if headers:
        proxy_headers.update(headers)
    if user_id:
        proxy_headers["X-User-Id"] = str(user_id)

    try:
        # 使用独立 client，生命周期由 stream_generator 管理
        client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
        # 发送请求但不读取 body（流式）
        request = client.build_request("POST", url, json=body, headers=proxy_headers)
        response = await client.send(request, stream=True)

        if response.status_code >= 400:
            error_body = (await response.aread()).decode()
            await client.aclose()
            raise HTTPException(
                status_code=response.status_code,
                detail=error_body,
            )

        async def stream_generator():
            try:
                async for chunk in response.aiter_text():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream; charset=utf-8",
            status_code=response.status_code,
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )
    except HTTPException:
        raise
    except httpx.RequestError as e:
        logger.error(f"Proxy stream request failed: {e}")
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")


# 笔记整理 Agent 路由
@app.post("/api/note/{path:path}")
async def proxy_note(request: Request, path: str):
    """转发到笔记整理 Agent（流式）"""
    user = await JWTAuth.get_current_user(request)
    body = await request.json()

    # 笔记整理使用 /organize/stream 端点
    stream_path = "/organize/stream"

    return await _proxy_stream_request(
        service_host=settings.AGENT_NOTE_HOST,
        service_port=settings.AGENT_NOTE_PORT,
        path=stream_path,
        body=body,
        user_id=user["user_id"],
    )


# 复习计划 Agent 路由
@app.post("/api/plan/{path:path}")
async def proxy_plan(request: Request, path: str):
    """转发到复习计划 Agent（流式）"""
    user = await JWTAuth.get_current_user(request)
    body = await request.json()

    # 复习计划使用 /generate/stream 端点
    stream_path = "/generate/stream"

    return await _proxy_stream_request(
        service_host=settings.AGENT_PLAN_HOST,
        service_port=settings.AGENT_PLAN_PORT,
        path=stream_path,
        body=body,
        user_id=user["user_id"],
    )


# 问答 Agent 路由 - 流式
@app.post("/api/qa/ask/stream")
async def proxy_qa_stream(request: Request):
    """转发到问答 Agent（流式）"""
    user = await JWTAuth.get_current_user(request)
    body = await request.json()

    return await _proxy_stream_request(
        service_host=settings.AGENT_QA_HOST,
        service_port=settings.AGENT_QA_PORT,
        path="/ask/stream",
        body=body,
        user_id=user["user_id"],
    )


# 问答 Agent 路由 - 非流式
@app.post("/api/qa/ask")
async def proxy_qa(request: Request):
    """转发到问答 Agent（非流式）"""
    user = await JWTAuth.get_current_user(request)
    body = await request.json()

    response = await _proxy_request(
        service_host=settings.AGENT_QA_HOST,
        service_port=settings.AGENT_QA_PORT,
        path="/ask",
        method="POST",
        body=body,
        user_id=user["user_id"],
    )
    return response.json()


@app.get("/api/qa/{path:path}")
@app.delete("/api/qa/{path:path}")
async def proxy_qa_other(request: Request, path: str):
    """转发到问答 Agent（非流式：历史记录等）"""
    user = await JWTAuth.get_current_user(request)
    body = {}
    if request.method == "GET":
        query_params = dict(request.query_params)
        body = query_params

    response = await _proxy_request(
        service_host=settings.AGENT_QA_HOST,
        service_port=settings.AGENT_QA_PORT,
        path=f"/{path}",
        method=request.method,
        body=body if body else None,
        user_id=user["user_id"],
    )
    return JSONResponse(
        content=response.json(),
        status_code=response.status_code,
    )


# 知识库路由（转发到 QA Agent）
@app.post("/api/knowledge/{path:path}")
async def proxy_knowledge_post(request: Request, path: str):
    """转发知识库 POST 请求到 QA Agent"""
    user = await JWTAuth.get_current_user(request)
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        # 文件上传：转发 form data
        form_data = await request.form()
        files = {}
        data = {}
        for key, value in form_data.items():
            if hasattr(value, "file"):
                import io
                files[key] = (value.filename, io.BytesIO(await value.read()), value.content_type)
            else:
                data[key] = value

        url = f"http://{settings.AGENT_QA_HOST}:{settings.AGENT_QA_PORT}/knowledge/{path}"
        proxy_headers = {"X-User-Id": str(user["user_id"])}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, data=data, files=files, headers=proxy_headers)
        return JSONResponse(content=response.json(), status_code=response.status_code)
    else:
        # JSON 请求
        body = await request.json()
        response = await _proxy_request(
            service_host=settings.AGENT_QA_HOST,
            service_port=settings.AGENT_QA_PORT,
            path=f"/knowledge/{path}",
            method="POST",
            body=body,
            user_id=user["user_id"],
        )
        return JSONResponse(content=response.json(), status_code=response.status_code)


@app.get("/api/knowledge/{path:path}")
async def proxy_knowledge_get(request: Request, path: str):
    """转发知识库 GET 请求到 QA Agent"""
    user = await JWTAuth.get_current_user(request)
    query_params = dict(request.query_params)

    response = await _proxy_request(
        service_host=settings.AGENT_QA_HOST,
        service_port=settings.AGENT_QA_PORT,
        path=f"/knowledge/{path}",
        method="GET",
        body=query_params if query_params else None,
        user_id=user["user_id"],
    )
    return JSONResponse(content=response.json(), status_code=response.status_code)


@app.delete("/api/knowledge/{path:path}")
async def proxy_knowledge_delete(request: Request, path: str):
    """转发知识库 DELETE 请求到 QA Agent"""
    user = await JWTAuth.get_current_user(request)

    response = await _proxy_request(
        service_host=settings.AGENT_QA_HOST,
        service_port=settings.AGENT_QA_PORT,
        path=f"/knowledge/{path}",
        method="DELETE",
        user_id=user["user_id"],
    )
    return JSONResponse(content=response.json(), status_code=response.status_code)


# ==================== 健康检查 ====================

@app.get("/health")
async def health_check():
    """网关健康检查"""
    redis_ok = await redis_client.ping()
    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "gateway",
        "redis": "connected" if redis_ok else "disconnected",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.gateway.main:app",
        host="0.0.0.0",
        port=settings.GATEWAY_PORT,
        reload=False,
    )
