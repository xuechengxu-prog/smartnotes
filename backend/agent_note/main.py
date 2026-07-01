"""
笔记整理 Agent 服务
提供笔记整理 API，使用 chains/note_chain
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from backend.chains.note_chain import note_chain
from backend.common.redis_client import redis_client
from backend.config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Pydantic 模型
class NoteOrganizeRequest(BaseModel):
    content: str = Field(..., min_length=1, description="原始笔记内容")
    style: Optional[str] = Field(None, description="整理风格要求")
    stream: bool = Field(False, description="是否流式输出")


class NoteOrganizeResponse(BaseModel):
    organized_note: str = Field(..., description="整理后的笔记")


# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Agent Note starting up...")
    await redis_client.connect()
    logger.info("Agent Note started.")
    yield
    logger.info("Agent Note shutting down...")
    await redis_client.close()
    logger.info("Agent Note stopped.")


app = FastAPI(
    title="SmartNotes - Note Agent",
    description="笔记整理 Agent 服务",
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


@app.post("/organize", response_model=NoteOrganizeResponse)
async def organize_note(request: NoteOrganizeRequest):
    """
    整理笔记（非流式）
    """
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    try:
        result = await note_chain.organize(
            content=request.content,
            style=request.style,
        )
        return NoteOrganizeResponse(organized_note=result)
    except Exception as e:
        logger.error(f"Note organization failed: {e}")
        raise HTTPException(status_code=500, detail=f"笔记整理失败: {str(e)}")


@app.post("/organize/stream")
async def organize_note_stream(request: NoteOrganizeRequest):
    """
    整理笔记（流式输出）
    """
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="笔记内容不能为空")

    from fastapi.responses import StreamingResponse

    async def generate():
        try:
            async for chunk in note_chain.organize_stream(
                content=request.content,
                style=request.style,
            ):
                if chunk and chunk.strip():
                    yield chunk
        except Exception as e:
            logger.error(f"Note stream failed: {e}")
            yield f"\n[错误] 笔记整理失败: {str(e)}"

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
    )


@app.get("/health")
async def health_check():
    """健康检查"""
    redis_ok = await redis_client.ping()
    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "agent_note",
        "redis": "connected" if redis_ok else "disconnected",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.agent_note.main:app",
        host="0.0.0.0",
        port=settings.AGENT_NOTE_PORT,
        reload=False,
    )
