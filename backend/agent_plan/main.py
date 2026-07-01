"""
复习计划 Agent 服务
提供复习计划生成 API，使用 chains/plan_chain
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.chains.plan_chain import plan_chain
from backend.common.redis_client import redis_client
from backend.config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Pydantic 模型
class PlanGenerateRequest(BaseModel):
    content: str = Field(..., min_length=1, description="笔记内容")
    days: int = Field(30, ge=1, le=365, description="计划总天数")
    sessions_per_day: int = Field(2, ge=1, le=10, description="每天复习次数")
    focus_areas: Optional[str] = Field(None, description="重点复习领域")
    stream: bool = Field(False, description="是否流式输出")


class PlanGenerateResponse(BaseModel):
    plan: str = Field(..., description="生成的复习计划")


class ScheduleResponse(BaseModel):
    schedule: list = Field(..., description="复习时间表")


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Agent Plan starting up...")
    await redis_client.connect()
    logger.info("Agent Plan started.")
    yield
    logger.info("Agent Plan shutting down...")
    await redis_client.close()
    logger.info("Agent Plan stopped.")


app = FastAPI(
    title="SmartNotes - Plan Agent",
    description="复习计划 Agent 服务",
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


@app.post("/generate", response_model=PlanGenerateResponse)
async def generate_plan(request: PlanGenerateRequest):
    """
    生成复习计划（非流式）
    """
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    try:
        result = await plan_chain.generate_plan(
            content=request.content,
            days=request.days,
            sessions_per_day=request.sessions_per_day,
            focus_areas=request.focus_areas,
        )
        return PlanGenerateResponse(plan=result)
    except Exception as e:
        logger.error(f"Plan generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"计划生成失败: {str(e)}")


@app.post("/generate/stream")
async def generate_plan_stream(request: PlanGenerateRequest):
    """
    生成复习计划（流式输出）
    """
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    from fastapi.responses import StreamingResponse

    async def generate():
        try:
            async for chunk in plan_chain.generate_plan_stream(
                content=request.content,
                days=request.days,
                sessions_per_day=request.sessions_per_day,
                focus_areas=request.focus_areas,
            ):
                # 必须累加所有 chunk，包括空白，否则 Markdown 格式会丢失
                if chunk is not None:
                    yield chunk
        except Exception as e:
            logger.error(f"Plan stream failed: {e}")
            yield f"\n[错误] 计划生成失败: {str(e)}"

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
    )


@app.post("/schedule", response_model=ScheduleResponse)
async def get_schedule(request: PlanGenerateRequest):
    """
    获取基于艾宾浩斯遗忘曲线的复习时间表
    """
    schedule = plan_chain.get_review_schedule(days=request.days)
    return ScheduleResponse(schedule=schedule)


@app.get("/health")
async def health_check():
    """健康检查"""
    redis_ok = await redis_client.ping()
    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "agent_plan",
        "redis": "connected" if redis_ok else "disconnected",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.agent_plan.main:app",
        host="0.0.0.0",
        port=settings.AGENT_PLAN_PORT,
        reload=False,
    )
