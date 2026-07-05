"""
Agent 工具集定义 v5.1
支持三种工具来源：
  1. 本地 Function Calling 工具（@tool 装饰器，通过 bind_tools 绑定到 LLM）
  2. MCP 工具（通过 langchain-mcp-adapters 加载的外部工具）
  3. 保留 AgentTools 核心实现（供 @tool 包装器内部调用）

升级说明：
  v5.0 -> v5.1
  - search_knowledge 支持 collection_name 参数，未指定时搜索用户所有 collection
  - add_knowledge 增加内容指纹去重，避免重复入库
"""
import hashlib
import json
import logging
import re
import uuid
from typing import Optional, List, Dict, Any

# 允许在已有事件循环中嵌套运行异步代码（uvicorn + LangChain 同步工具调用场景）
import nest_asyncio
nest_asyncio.apply()

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import tool

from backend.common.chroma_client import chroma_client
from backend.common.redis_client import redis_client
from backend.services.llm_service import llm_service
from backend.rag.enhanced_rag import (
    QueryRewriter,
    DataCleaner,
    SmartChunker,
    HybridRetriever,
)

logger = logging.getLogger(__name__)


# ============================================================
# 核心实现层（保留原有逻辑，供 @tool 包装器调用）
# ============================================================

class AgentTools:
    """Agent 工具核心实现 - 保持原有业务逻辑不变"""

    # 类级别的工具调用记录（用于回答"你用了哪些工具"）
    _tool_calls: Dict[str, List[Dict[str, Any]]] = {}

    @classmethod
    def record_tool_call(cls, session_id: str, tool_name: str, tool_input: Dict, tool_output: str):
        """记录工具调用历史"""
        if session_id not in cls._tool_calls:
            cls._tool_calls[session_id] = []
        cls._tool_calls[session_id].append({
            "tool": tool_name,
            "input": tool_input,
            "output": tool_output[:200] if len(tool_output) > 200 else tool_output,
            "timestamp": str(uuid.uuid4())
        })
        cls._tool_calls[session_id] = cls._tool_calls[session_id][-20:]

    @classmethod
    def get_tool_calls(cls, session_id: str) -> List[Dict[str, Any]]:
        """获取当前会话的工具调用记录"""
        return cls._tool_calls.get(session_id, [])

    @classmethod
    def clear_tool_calls(cls, session_id: str):
        """清除工具调用记录"""
        if session_id in cls._tool_calls:
            del cls._tool_calls[session_id]

    @staticmethod
    def _get_user_collection(user_id: int, collection_name: Optional[str] = None) -> str:
        """获取用户隔离的 collection 名称"""
        if collection_name:
            return f"user_{user_id}_{collection_name}"
        return f"user_{user_id}_default"

    @staticmethod
    def _get_user_collections(user_id: int) -> List[str]:
        """获取用户的所有 collection 名称"""
        try:
            all_collections = chroma_client.list_collections()
            prefix = f"user_{user_id}_"
            return [c for c in all_collections if c.startswith(prefix)]
        except Exception as e:
            logger.warning(f"获取用户 collection 列表失败: {e}")
            return []

    @staticmethod
    def _search_single_collection(query: str, user_collection: str, n_results: int = 5) -> Optional[List[Dict]]:
        """搜索单个 collection，返回结果列表"""
        try:
            retriever = HybridRetriever()
            result = retriever.retrieve_sync(
                query=query,
                collection_name=user_collection,
                n_results=n_results,
                use_multi_query=True,
                use_hyde=False,
                use_mmr=True,
            )
            if result and result.get("results"):
                return result["results"]
        except Exception as e:
            logger.warning(f"混合检索 {user_collection} 失败，尝试基础检索: {e}")
            try:
                semantic_results = chroma_client.search(
                    collection_name=user_collection,
                    query_text=query,
                    n_results=n_results,
                )
                if semantic_results and semantic_results.get("documents"):
                    docs = semantic_results["documents"][0]
                    metadatas = semantic_results.get("metadatas", [[]])[0]
                    results = []
                    for i, doc in enumerate(docs[:n_results]):
                        meta = metadatas[i] if i < len(metadatas) else {}
                        results.append({
                            "id": semantic_results.get("ids", [[]])[0][i] if i < len(semantic_results.get("ids", [[]])[0]) else str(i),
                            "doc": doc,
                            "metadata": meta,
                            "score": 1.0,
                        })
                    return results
            except Exception as fallback_e:
                logger.error(f"基础检索也失败: {fallback_e}")
        return None

    @staticmethod
    def search_knowledge_impl(user_id: int, query: str, n_results: int = 5,
                              collection_name: Optional[str] = None,
                              session_id: Optional[str] = None) -> str:
        """搜索知识库实现（语义+BM25+RRF+MMR 混合检索）
        如果没有指定 collection_name，会自动搜索用户的所有 collection。
        """
        # 确定要搜索的 collection 列表
        collections_to_search = []
        if collection_name:
            collections_to_search = [AgentTools._get_user_collection(user_id, collection_name)]
        else:
            user_collections = AgentTools._get_user_collections(user_id)
            if user_collections:
                collections_to_search = user_collections
            else:
                collections_to_search = [AgentTools._get_user_collection(user_id, None)]

        logger.info(f"知识库搜索: query='{query}', collections={collections_to_search}")

        # 搜索所有 collection，合并结果
        all_results = []
        for user_collection in collections_to_search:
            results = AgentTools._search_single_collection(query, user_collection, n_results)
            if results:
                all_results.extend(results)

        if not all_results:
            result_text = "知识库中未找到相关内容。"
            if session_id:
                AgentTools.record_tool_call(session_id, "search_knowledge",
                                            {"query": query, "collections": collections_to_search}, result_text)
            return result_text

        # 去重并排序（按 score 降序）
        seen_docs = set()
        unique_results = []
        for item in all_results:
            doc = item.get("doc", "")
            doc_key = doc[:150]
            if doc_key not in seen_docs:
                seen_docs.add(doc_key)
                unique_results.append(item)

        unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_results = unique_results[:n_results]

        parts = []
        for i, item in enumerate(top_results):
            source = item.get("metadata", {}).get("filename", f"文档{i+1}")
            parts.append(f"[来源: {source}]\n{item['doc']}")

        result_text = "\n\n---\n\n".join(parts)
        logger.info(f"知识库检索完成: collections={collections_to_search}, unique_results={len(unique_results)}, returned={len(top_results)}")

        if session_id:
            AgentTools.record_tool_call(session_id, "search_knowledge",
                                        {"query": query, "collections": collections_to_search}, result_text)
        return result_text

    @staticmethod
    def add_knowledge_impl(user_id: int, text: str, collection_name: Optional[str] = None,
                           session_id: Optional[str] = None) -> str:
        """添加知识到知识库实现（DataCleaner + SmartChunker 智能切片，带去重）"""
        try:
            if not text or not text.strip():
                result = "错误：保存内容不能为空。请提供具体内容后再保存。"
                if session_id:
                    AgentTools.record_tool_call(session_id, "add_knowledge", {"text": text}, result)
                return result

            user_collection = AgentTools._get_user_collection(user_id, collection_name)
            cleaned_text = DataCleaner.clean_text(text)
            if not cleaned_text.strip():
                result = "错误：清洗后内容为空，请提供更有实质内容的文本。"
                if session_id:
                    AgentTools.record_tool_call(session_id, "add_knowledge", {"text": text[:100]}, result)
                return result

            # 内容指纹去重：用 MD5 检查是否已存在相同内容
            content_fingerprint = hashlib.md5(cleaned_text[:2000].encode('utf-8')).hexdigest()
            try:
                collection = chroma_client.get_or_create_collection(user_collection)
                existing = collection.get(ids=[content_fingerprint])
                if existing and existing.get("ids") and len(existing["ids"]) > 0:
                    result = "该内容已存在于知识库中，无需重复添加。"
                    if session_id:
                        AgentTools.record_tool_call(session_id, "add_knowledge",
                                                    {"text": text[:100]}, result)
                    return result
            except Exception as dup_e:
                logger.warning(f"去重检查异常，继续添加: {dup_e}")

            chunker = SmartChunker(chunk_size=500, chunk_overlap=50)
            chunk_texts, chunk_metadatas = chunker.chunk_documents(
                [cleaned_text],
                [{"user_id": str(user_id), "type": "manual_add", "source": "agent_save"}]
            )

            # 第一个切片使用内容指纹作为稳定 ID，其余使用 uuid
            chunk_ids = [content_fingerprint]
            if len(chunk_texts) > 1:
                chunk_ids.extend([str(uuid.uuid4()) for _ in range(len(chunk_texts) - 1)])

            chroma_client.add_texts(
                collection_name=user_collection,
                texts=chunk_texts,
                metadatas=chunk_metadatas,
                ids=chunk_ids,
            )

            result = f"知识已添加到知识库（{len(chunk_texts)} 个切片已入库）"
            if session_id:
                AgentTools.record_tool_call(session_id, "add_knowledge",
                                            {"text": text[:100] + "..." if len(text) > 100 else text}, result)
            return result
        except Exception as e:
            logger.error(f"Add knowledge failed: {e}")
            error_msg = f"添加知识失败: {str(e)}"
            if session_id:
                AgentTools.record_tool_call(session_id, "add_knowledge", {"text": text}, error_msg)
            return error_msg

    @staticmethod
    def query_rewrite(original_query: str, history: List[Dict[str, str]] = None) -> str:
        """查询改写：结合指代消解 + LLM Multi-Query"""
        query = original_query.strip()

        pronouns = ["这个", "那个", "刚才", "之前", "上面", "这些", "那些"]
        has_pronoun = any(p in query for p in pronouns)

        if has_pronoun and history:
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    context = content[:100] + "..." if len(content) > 100 else content
                    query = f"基于之前的讨论（{context}），用户问：{query}"
                    break

        try:
            rewrite_prompt = ChatPromptTemplate.from_messages([
                ("human", """请将以下用户查询改写为更适合知识库检索的形式。
规则：
1. 补全省略的主语和上下文
2. 将口语化表述转换为正式表述
3. 提取核心关键词
4. 只输出改写后的查询，不要解释
5. 如果原始查询已经很清晰，保持不变

原始查询: {query}
改写后的查询:"""),
            ])
            chain = rewrite_prompt | llm_service.llm | StrOutputParser()
            rewritten = chain.invoke({"query": query})
            if rewritten and rewritten.strip():
                logger.info(f"Query rewrite (LLM): '{query}' -> '{rewritten.strip()}'")
                return rewritten.strip()
        except Exception as e:
            logger.warning(f"LLM query rewrite failed, using rule-based result: {e}")

        return query


# ============================================================
# LangChain Function Calling 工具（@tool 装饰器）
# 这些工具通过 bind_tools() 绑定到 LLM，实现原生 Function Calling
# ============================================================

def create_local_tools(user_id: int, session_id: str):
    """
    创建本地 LangChain 工具列表（闭包注入 user_id 和 session_id）
    返回的 Tool 对象可以通过 bind_tools() 绑定到 LLM
    """
    _user_id = user_id
    _session_id = session_id

    @tool
    def search_knowledge(query: str, collection_name: str = "", n_results: int = 5) -> str:
        """搜索用户知识库，使用混合检索（语义+BM25+RRF+MMR）。
        当用户的问题可能与知识库中保存的笔记、学习内容相关时使用此工具。
        参数 query 是搜索关键词或问题。
        参数 collection_name 是知识库名称（可选，不填则搜索用户所有知识库）。
        参数 n_results 是返回结果数量。"""
        return AgentTools.search_knowledge_impl(
            user_id=_user_id,
            query=query,
            n_results=n_results,
            collection_name=collection_name if collection_name.strip() else None,
            session_id=_session_id,
        )

    @tool
    def add_knowledge(text: str, collection_name: str = "") -> str:
        """将新知识添加到用户的个人知识库。
        当用户说"保存"、"记录"、"存到知识库"时使用此工具。
        参数 text 是要保存的完整文本内容（至少50字）。
        参数 collection_name 是知识库名称（可选，不填则使用默认知识库）。"""
        return AgentTools.add_knowledge_impl(
            user_id=_user_id,
            text=text,
            collection_name=collection_name if collection_name.strip() else None,
            session_id=_session_id,
        )

    @tool
    def calculator(expression: str) -> str:
        """数学计算器，计算数学表达式的结果。
        当用户问数学问题或需要数值计算时使用此工具。
        参数 expression 是数学表达式，如 '2+3*4'、'(1+2)*3'。"""
        try:
            allowed = set("0123456789+-*/.()^% ")
            if not all(c in allowed for c in expression):
                return f"错误：表达式 '{expression}' 包含非法字符。"
            safe_expr = expression.replace("^", "**")
            result = eval(safe_expr, {"__builtins__": {}}, {})
            AgentTools.record_tool_call(_session_id, "calculator", {"expression": expression}, f"计算结果: {result}")
            return f"计算结果: {result}"
        except Exception as e:
            error_msg = f"计算错误: {str(e)}"
            AgentTools.record_tool_call(_session_id, "calculator", {"expression": expression}, error_msg)
            return error_msg

    return [search_knowledge, add_knowledge, calculator]
