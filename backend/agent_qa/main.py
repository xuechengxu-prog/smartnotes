"""
问答 Agent 服务 - v5.0 ReAct Agent + Function Calling + MCP
提供智能问答 API，基于 LangGraph + MCP 架构
支持工具调用（本地 Function Calling + MCP 外部工具）、对话记忆、流式输出

v5.0 升级：
  1. ReAct Prompt + Function Calling（LangGraph StateGraph + bind_tools）
  2. MCP 工具集成（联网搜索、学习辅助）
  3. 工具来源统一管理（本地 @tool + MCP adapters）
"""
import hashlib
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.agent_qa.agent_core import create_agent
from backend.agent_qa.tools import AgentTools
from backend.chains.qa_chain import qa_chain
from backend.common.redis_client import redis_client
from backend.common.chroma_client import chroma_client
from backend.common.database import (
    init_database, close_database, get_db_session,
    KnowledgeItem,
)
from backend.rag.enhanced_rag import DataCleaner, SmartChunker
from backend.config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# MCP 工具管理器
# ============================================================

class MCPToolManager:
    """管理 MCP Server 连接和工具加载"""

    _instance: Optional["MCPToolManager"] = None
    _mcp_tools: list = []
    _initialized: bool = False

    def __new__(cls) -> "MCPToolManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        """初始化 MCP 连接，加载外部工具（带重试）"""
        if self._initialized:
            return

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            import asyncio

            mcp_servers = {}

            if settings.WEB_SEARCH_MCP_URL:
                mcp_servers["web_search"] = {
                    "url": settings.WEB_SEARCH_MCP_URL,
                    "transport": "streamable_http",
                }

            if settings.SMARTNOTES_MCP_URL:
                mcp_servers["smartnotes_learning"] = {
                    "url": settings.SMARTNOTES_MCP_URL,
                    "transport": "streamable_http",
                }

            if mcp_servers:
                # 最多重试 3 次，每次间隔 3 秒（等待 MCP Server 就绪）
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        self._client = MultiServerMCPClient(mcp_servers)
                        self._mcp_tools = await self._client.get_tools()
                        tool_names = [t.name for t in self._mcp_tools]
                        logger.info(f"MCP 工具加载成功: {tool_names}")
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.info(f"MCP 连接第 {attempt+1} 次失败，{3}秒后重试...")
                            await asyncio.sleep(3)
                        else:
                            import traceback
                            logger.warning(f"MCP 工具加载失败（将仅使用本地工具）: {e}\n{traceback.format_exc()}")
                            self._mcp_tools = []
            else:
                logger.info("未配置 MCP Server，仅使用本地 Function Calling 工具")

        except ImportError:
            logger.warning("langchain-mcp-adapters 未安装，将仅使用本地工具")
            self._mcp_tools = []
        except Exception as e:
            logger.warning(f"MCP 初始化失败: {e}")
            self._mcp_tools = []

        self._initialized = True

    async def close(self):
        """关闭 MCP 连接"""
        if hasattr(self, '_client'):
            try:
                await self._client.close()
            except:
                pass
        self._initialized = False
        self._mcp_tools = []

    @property
    def mcp_tools(self) -> list:
        return self._mcp_tools


mcp_manager = MCPToolManager()


# ============================================================
# Pydantic 模型
# ============================================================

class QARequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    context: Optional[str] = Field(None, description="知识库上下文（可选，不传则让 Agent 自主决定）")
    stream: bool = Field(False, description="是否流式输出")
    use_cache: bool = Field(True, description="是否使用缓存（Agent 模式暂不使用）")
    session_id: Optional[str] = Field(None, description="会话ID（不传则创建新会话）")
    use_agent: bool = Field(True, description="是否使用 ReAct Agent（true=Agent模式, false=传统RAG模式）")


class QAResponse(BaseModel):
    answer: str = Field(..., description="回答内容")
    cache_hit: bool = Field(False, description="是否命中缓存")
    session_id: str = Field("", description="会话ID")
    thoughts: List[str] = Field([], description="Agent 思考过程")
    actions: List[dict] = Field([], description="Agent 执行的工具调用")
    used_tools: List[str] = Field([], description="本次对话使用的工具列表")
    source: str = Field("", description="回答来源: knowledge_base / llm / web_search")


class KnowledgeAddTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="要添加的文本内容")
    collection_name: Optional[str] = Field(None, description="集合名称（可选）")


class KnowledgeSearchResponse(BaseModel):
    results: list = Field(..., description="搜索结果列表")


# ============================================================
# 生命周期管理
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Agent QA v5.0 starting up...")
    await redis_client.connect()
    await init_database()
    await mcp_manager.initialize()
    logger.info("Agent QA v5.0 started (ReAct + Function Calling + MCP).")
    yield
    logger.info("Agent QA shutting down...")
    await mcp_manager.close()
    await close_database()
    await redis_client.close()
    logger.info("Agent QA stopped.")


app = FastAPI(
    title="SmartNotes - QA Agent v5.0",
    description="问答 Agent 服务（ReAct Prompt + Function Calling + MCP）",
    version="5.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 工具函数
# ============================================================

def _get_user_collection(user_id: int, collection_name: Optional[str] = None) -> str:
    if collection_name:
        return f"user_{user_id}_{collection_name}"
    return f"user_{user_id}_default"


def _generate_cache_key(question: str, context: Optional[str] = None) -> str:
    key_content = f"qa:{settings.LLM_MODEL}:{question}:{context or ''}"
    return hashlib.md5(key_content.encode()).hexdigest()


def _build_context_from_search_results(results: dict) -> str:
    if not results or not results.get("documents"):
        return ""
    documents = results["documents"]
    metadatas = results.get("metadatas", [[] for _ in documents])
    parts = []
    for i, doc_list in enumerate(documents):
        for j, doc in enumerate(doc_list):
            meta = metadatas[i][j] if i < len(metadatas) and j < len(metadatas[i]) else {}
            source = meta.get("filename", "未知来源")
            parts.append(f"[文档 {j+1} - {source}]\n{doc}")
    return "\n\n---\n\n".join(parts) if parts else ""


async def _save_qa_to_chromadb(user_id: int, question: str, answer: str):
    try:
        qa_text = f"问题：{question}\n\n回答：{answer}"
        item_id = f"qa_{user_id}_{uuid.uuid4().hex[:8]}"
        collection = _get_user_collection(user_id)
        chroma_client.add_texts(
            collection_name=collection,
            texts=[qa_text],
            metadatas=[{"user_id": str(user_id), "type": "qa_record", "question": question[:200]}],
            ids=[item_id],
        )
    except Exception as e:
        logger.error(f"Failed to save QA to ChromaDB: {e}")


def _parse_file_content(filename: str, content: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("txt", "md"):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("gbk", errors="ignore")
    elif ext == "pdf":
        raise HTTPException(status_code=400, detail="PDF 解析需要额外依赖，当前暂不支持")
    elif ext == "docx":
        raise HTTPException(status_code=400, detail="DOCX 解析需要额外依赖，当前暂不支持")
    else:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: .{ext}")


# ============================================================
# 问答路由 - Agent 模式 (ReAct + Function Calling + MCP)
# ============================================================

@app.post("/ask", response_model=QAResponse)
async def ask_question(request: QARequest, x_user_id: int = Header(...)):
    """问答（非流式）- Agent 模式自动使用 Function Calling + MCP 工具"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    if request.use_agent:
        agent = await create_agent(
            user_id=x_user_id,
            session_id=request.session_id,
            mcp_tools=mcp_manager.mcp_tools,
        )
        result = await agent.run(request.question)

        # 判断来源
        source = result.get("source", "llm")
        if any("web_search" in t or "search_and_summarize" in t or "get_web_content" in t
               for t in result.get("used_tools", [])):
            source = "web_search"

        return QAResponse(
            answer=result["answer"],
            session_id=result["session_id"],
            thoughts=result.get("thoughts", []),
            actions=result.get("actions", []),
            used_tools=result.get("used_tools", []),
            source=source,
        )

    # 传统 RAG 模式（向后兼容）
    cache_key = None
    cache_hit = False
    answer = None

    context = request.context
    if not context:
        try:
            user_collection = _get_user_collection(x_user_id)
            search_results = chroma_client.search(
                collection_name=user_collection,
                query_text=request.question,
                n_results=5,
            )
            context = _build_context_from_search_results(search_results)
        except Exception as e:
            logger.warning(f"ChromaDB search failed: {e}")
            context = ""

    if request.use_cache:
        cache_key = _generate_cache_key(request.question, context)
        cached = await redis_client.cache_get(cache_key)
        if cached:
            answer = cached
            cache_hit = True

    if answer is None:
        try:
            full_answer = ""
            async for chunk in qa_chain.answer_stream(
                question=request.question,
                context=context or "",
            ):
                full_answer += chunk
            answer = full_answer
        except Exception as e:
            logger.error(f"QA failed: {e}")
            raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")

        if request.use_cache and cache_key:
            await redis_client.cache_set(cache_key, answer, ttl=settings.CACHE_TTL)

    await _save_qa_to_chromadb(x_user_id, request.question, answer)
    return QAResponse(answer=answer, cache_hit=cache_hit)


@app.post("/ask/stream")
async def ask_question_stream(request: QARequest, x_user_id: int = Header(...)):
    """问答（流式输出）- Agent 模式实时展示 Thought/Action/Observation"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    if request.use_agent:
        agent = await create_agent(
            user_id=x_user_id,
            session_id=request.session_id,
            mcp_tools=mcp_manager.mcp_tools,
        )

        async def agent_stream():
            yield f"data: {json.dumps({'type': 'session_id', 'session_id': agent.session_id}, ensure_ascii=False)}\n\n"
            async for event in agent.run_stream(request.question):
                event_json = json.dumps(event, ensure_ascii=False)
                yield f"data: {event_json}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            agent_stream(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # 传统 RAG 流式模式（向后兼容）
    context = request.context
    if not context:
        try:
            user_collection = _get_user_collection(x_user_id)
            search_results = chroma_client.search(
                collection_name=user_collection,
                query_text=request.question,
                n_results=5,
            )
            context = _build_context_from_search_results(search_results)
        except Exception as e:
            logger.warning(f"ChromaDB search failed: {e}")
            context = ""

    answer_parts = []

    async def generate():
        try:
            async for chunk in qa_chain.answer_stream(
                question=request.question,
                context=context or "",
            ):
                answer_parts.append(chunk)
                yield chunk
        except Exception as e:
            logger.error(f"QA stream failed: {e}")
            yield f"\n[错误] 问答失败: {str(e)}"

    async def stream_with_save():
        async for chunk in generate():
            yield chunk
        full_answer = "".join(answer_parts)
        if full_answer:
            await _save_qa_to_chromadb(x_user_id, request.question, full_answer)

    return StreamingResponse(
        stream_with_save(),
        media_type="text/plain; charset=utf-8",
    )


# ============================================================
# 知识库路由
# ============================================================

@app.post("/knowledge/add/text")
async def add_text_to_knowledge(
    request: KnowledgeAddTextRequest,
    x_user_id: int = Header(...),
):
    """添加文本到知识库（增强版：数据清洗 + 智能切片 + 去重）"""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="文本内容不能为空")

    try:
        user_collection = _get_user_collection(x_user_id, request.collection_name)
        cleaned_text = DataCleaner.clean_text(request.text)
        if not cleaned_text.strip():
            raise HTTPException(status_code=400, detail="清洗后文本内容为空")

        # 内容指纹去重
        content_fingerprint = hashlib.md5(cleaned_text[:2000].encode('utf-8')).hexdigest()
        try:
            collection = chroma_client.get_or_create_collection(user_collection)
            existing = collection.get(ids=[content_fingerprint])
            if existing and existing.get("ids") and len(existing["ids"]) > 0:
                return {
                    "message": "该内容已存在于知识库中，无需重复添加。",
                    "duplicate": True,
                    "collection_name": user_collection,
                }
        except Exception as dup_e:
            logger.warning(f"去重检查异常，继续添加: {dup_e}")

        chunker = SmartChunker(chunk_size=500, chunk_overlap=50)
        chunk_texts, chunk_metadatas = chunker.chunk_documents(
            [cleaned_text],
            [{"user_id": str(x_user_id), "source": "text_upload"}]
        )

        # 第一个切片使用指纹 ID，其余使用 uuid
        item_ids = [content_fingerprint]
        if len(chunk_texts) > 1:
            item_ids.extend([str(uuid.uuid4()) for _ in range(len(chunk_texts) - 1)])

        try:
            chroma_client.add_texts(
                collection_name=user_collection,
                texts=chunk_texts,
                metadatas=chunk_metadatas,
                ids=item_ids,
            )
        except Exception as e:
            logger.error(f"ChromaDB add_texts failed: {e}")
            raise HTTPException(status_code=503, detail=f"知识库服务暂时不可用，请稍后重试。错误: {str(e)}")

        session = await get_db_session()
        try:
            knowledge_item = KnowledgeItem(
                user_id=x_user_id,
                collection_name=user_collection,
                content=request.text[:500] + ("..." if len(request.text) > 500 else ""),
                chroma_id=item_ids[0],
            )
            session.add(knowledge_item)
            await session.commit()
            await session.refresh(knowledge_item)
            db_id = knowledge_item.id
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

        return {
            "message": f"文本已添加到知识库（清洗后 {len(cleaned_text)} 字 -> {len(chunk_texts)} 个智能切片）",
            "chroma_ids": item_ids,
            "db_id": db_id,
            "collection_name": user_collection,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add text to knowledge: {e}")
        raise HTTPException(status_code=500, detail=f"添加文本失败: {str(e)}")


@app.post("/knowledge/add/file")
async def add_file_to_knowledge(
    file: UploadFile = File(...),
    collection_name: Optional[str] = Query(None, description="集合名称"),
    x_user_id: int = Header(...),
):
    """上传文件到知识库（增强版：数据清洗 + 智能切片 + 去重）"""
    try:
        content_bytes = await file.read()
        if not content_bytes:
            raise HTTPException(status_code=400, detail="文件内容为空")

        text_content = _parse_file_content(file.filename, content_bytes)
        user_collection = _get_user_collection(x_user_id, collection_name)

        cleaned_text = DataCleaner.clean_text(text_content)
        if not cleaned_text.strip():
            raise HTTPException(status_code=400, detail="文件清洗后内容为空")

        # 内容指纹去重
        content_fingerprint = hashlib.md5(cleaned_text[:2000].encode('utf-8')).hexdigest()
        try:
            collection = chroma_client.get_or_create_collection(user_collection)
            existing = collection.get(ids=[content_fingerprint])
            if existing and existing.get("ids") and len(existing["ids"]) > 0:
                return {
                    "message": f"文件 '{file.filename}' 的内容已存在于知识库中，无需重复添加。",
                    "duplicate": True,
                    "collection_name": user_collection,
                }
        except Exception as dup_e:
            logger.warning(f"去重检查异常，继续添加: {dup_e}")

        chunker = SmartChunker(chunk_size=500, chunk_overlap=50)
        chunk_texts, chunk_metadatas = chunker.chunk_documents(
            [cleaned_text],
            [{"user_id": str(x_user_id), "filename": file.filename, "source": "file_upload"}]
        )

        # 第一个切片使用指纹 ID，其余使用 uuid
        item_ids = [content_fingerprint]
        if len(chunk_texts) > 1:
            item_ids.extend([str(uuid.uuid4()) for _ in range(len(chunk_texts) - 1)])

        chroma_client.add_texts(
            collection_name=user_collection,
            texts=chunk_texts,
            metadatas=chunk_metadatas,
            ids=item_ids,
        )

        session = await get_db_session()
        try:
            knowledge_item = KnowledgeItem(
                user_id=x_user_id,
                collection_name=user_collection,
                content=cleaned_text[:500] + ("..." if len(cleaned_text) > 500 else ""),
                filename=file.filename,
                chroma_id=item_ids[0],
            )
            session.add(knowledge_item)
            await session.commit()
            await session.refresh(knowledge_item)
            db_id = knowledge_item.id
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

        return {
            "message": f"文件 '{file.filename}' 已添加到知识库（清洗后 {len(cleaned_text)} 字 -> {len(chunk_texts)} 个智能切片）",
            "chroma_ids": item_ids,
            "db_id": db_id,
            "collection_name": user_collection,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add file to knowledge: {e}")
        raise HTTPException(status_code=500, detail=f"添加文件失败: {str(e)}")


@app.get("/knowledge/collections")
async def list_user_collections(x_user_id: int = Header(...)):
    """列出当前用户的所有知识库 collection 名称"""
    try:
        all_collections = chroma_client.list_collections()
        prefix = f"user_{x_user_id}_"
        user_collections = []
        for c in all_collections:
            if c.startswith(prefix):
                # 提取 collection_name 部分：user_{id}_{name} -> {name}
                name = c[len(prefix):]
                user_collections.append(name)
        # 始终包含 default
        if "default" not in user_collections:
            user_collections.insert(0, "default")
        return {"collections": user_collections}
    except Exception as e:
        logger.error(f"List collections failed: {e}")
        return {"collections": ["default"]}


class CreateCollectionRequest(BaseModel):
    collection_name: str = Field(..., min_length=1, max_length=100, description="知识库名称")


@app.post("/knowledge/collections")
async def create_collection(
    request: CreateCollectionRequest,
    x_user_id: int = Header(...),
):
    """创建新的知识库 collection（预创建空 collection）"""
    name = request.collection_name.strip()
    # 验证名称格式
    valid_name_regex = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$')
    if not valid_name_regex.match(name):
        raise HTTPException(
            status_code=400,
            detail="知识库名称只能包含字母、数字、下划线、中划线，且不能以特殊字符开头或结尾"
        )

    user_collection = _get_user_collection(x_user_id, name)
    try:
        # 预创建 collection（如果已存在则返回已有）
        chroma_client.get_or_create_collection(user_collection)
        return {"message": f"知识库 '{name}' 创建成功", "collection_name": name}
    except Exception as e:
        logger.error(f"Create collection failed: {e}")
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {str(e)}")


@app.get("/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    query: str = Query(..., min_length=1, description="搜索关键词"),
    collection_name: Optional[str] = Query(None, description="集合名称"),
    n_results: int = Query(5, ge=1, le=20, description="返回结果数量"),
    x_user_id: int = Header(...),
):
    """搜索知识库"""
    try:
        user_collection = _get_user_collection(x_user_id, collection_name)
        results = None
        try:
            results = chroma_client.search(
                collection_name=user_collection,
                query_text=query,
                n_results=n_results,
            )
        except Exception as e:
            logger.warning(f"ChromaDB search failed: {e}")
            return KnowledgeSearchResponse(results=[])

        formatted = []
        if results and results.get("documents"):
            documents = results["documents"]
            metadatas = results.get("metadatas", [[] for _ in documents])
            distances = results.get("distances", [[] for _ in documents])
            ids = results.get("ids", [[] for _ in documents])

            for i, doc_list in enumerate(documents):
                for j, doc in enumerate(doc_list):
                    meta = metadatas[i][j] if i < len(metadatas) and j < len(metadatas[i]) else {}
                    distance = distances[i][j] if i < len(distances) and j < len(distances[i]) else None
                    doc_id = ids[i][j] if i < len(ids) and j < len(ids[i]) else None
                    formatted.append({
                        "id": doc_id,
                        "content": doc,
                        "metadata": meta,
                        "distance": distance,
                    })

        return KnowledgeSearchResponse(results=formatted)
    except Exception as e:
        logger.error(f"Failed to search knowledge: {e}")
        raise HTTPException(status_code=500, detail=f"搜索知识库失败: {str(e)}")


@app.delete("/knowledge/{item_id}")
async def delete_knowledge_item(item_id: int, x_user_id: int = Header(...)):
    """删除知识库条目"""
    try:
        session = await get_db_session()
        try:
            result = await session.execute(
                select(KnowledgeItem).where(
                    KnowledgeItem.id == item_id,
                    KnowledgeItem.user_id == x_user_id,
                )
            )
            item = result.scalar_one_or_none()
            if not item:
                raise HTTPException(status_code=404, detail="知识库条目不存在")

            try:
                collection = chroma_client.get_or_create_collection(item.collection_name)
                collection.delete(ids=[item.chroma_id])
            except Exception as ce:
                logger.warning(f"Failed to delete from ChromaDB: {ce}")

            await session.delete(item)
            await session.commit()
            return {"message": "知识库条目已删除"}
        except HTTPException:
            raise
        finally:
            await session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete knowledge item: {e}")
        raise HTTPException(status_code=500, detail=f"删除知识库条目失败: {str(e)}")


# ============================================================
# 会话管理路由
# ============================================================

@app.get("/sessions")
async def list_sessions(x_user_id: int = Header(...)):
    """列出用户的所有会话"""
    try:
        pattern = f"agent:history:{x_user_id}:*"
        keys = []
        cursor = 0
        while True:
            cursor, batch = await redis_client.client.scan(cursor=cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        sessions = []
        for key in keys:
            parts = key.split(":")
            if len(parts) >= 4:
                session_id = parts[3]
                length = await redis_client.client.llen(key)
                title = ""
                if length > 0:
                    first_msg_raw = await redis_client.client.lindex(key, 0)
                    if first_msg_raw:
                        try:
                            first_msg = json.loads(first_msg_raw)
                            if first_msg.get('role') == 'user':
                                content = first_msg.get('content', '')
                                title = content[:30] + ('...' if len(content) > 30 else '')
                        except Exception as e:
                            logger.error(f"Parse session title failed: {e}")
                meta_key = f"agent:session_meta:{x_user_id}:{session_id}"
                meta_data = await redis_client.client.hgetall(meta_key)
                updated_at = float(meta_data.get("updated_at", 0)) if meta_data else 0
                sessions.append({
                    "session_id": session_id,
                    "message_count": length,
                    "title": title,
                    "updated_at": updated_at
                })
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"List sessions failed: {e}")
        return {"sessions": []}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, x_user_id: int = Header(...)):
    """删除指定会话"""
    try:
        key = f"agent:history:{x_user_id}:{session_id}"
        await redis_client.client.delete(key)
        return {"message": "会话已删除"}
    except Exception as e:
        logger.error(f"Delete session failed: {e}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, x_user_id: int = Header(...)):
    """获取指定会话的历史消息"""
    try:
        key = f"agent:history:{x_user_id}:{session_id}"
        history_raw = await redis_client.client.lrange(key, 0, -1)
        history = []
        for item in history_raw:
            try:
                msg = json.loads(item)
                history.append({
                    "role": msg.get("role", "unknown"),
                    "content": msg.get("content", "")
                })
            except:
                continue
        return {"history": history}
    except Exception as e:
        logger.error(f"Get session history failed: {e}")
        return {"history": []}


# ============================================================
# 工具信息路由（新增）
# ============================================================

@app.get("/tools")
async def list_available_tools():
    """列出 Agent 当前可用的所有工具（本地 + MCP）"""
    tools_info = []

    # 本地 Function Calling 工具
    local_tool_names = ["search_knowledge", "add_knowledge", "calculator"]
    for name in local_tool_names:
        tools_info.append({
            "name": name,
            "source": "local_function_calling",
            "description": {
                "search_knowledge": "搜索用户知识库（混合检索）",
                "add_knowledge": "添加知识到用户知识库",
                "calculator": "数学计算器",
            }.get(name, ""),
        })

    # MCP 工具
    for tool in mcp_manager.mcp_tools:
        tools_info.append({
            "name": tool.name,
            "source": "mcp",
            "description": tool.description or "",
        })

    return {"tools": tools_info, "total": len(tools_info)}


# ============================================================
# 健康检查
# ============================================================

@app.get("/health")
async def health_check():
    """健康检查"""
    redis_ok = await redis_client.ping()
    mcp_tool_count = len(mcp_manager.mcp_tools)
    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "agent_qa",
        "version": "5.0.0",
        "mode": "react_function_calling_mcp",
        "redis": "connected" if redis_ok else "disconnected",
        "mcp_tools": mcp_tool_count,
        "architecture": "ReAct Prompt + Function Calling + MCP",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.agent_qa.main:app",
        host="0.0.0.0",
        port=settings.AGENT_QA_PORT,
        reload=False,
    )
