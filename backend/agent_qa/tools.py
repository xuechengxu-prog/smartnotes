"""
Agent 工具集定义 v2.0
为 ReAct Agent 提供可调用工具
新增：query改写、BM25+语义多路召回、工具调用追踪
"""
import json
import logging
import re
import uuid
from typing import Optional, List, Dict, Any, Tuple
from collections import Counter

from backend.common.chroma_client import chroma_client
from backend.common.redis_client import redis_client
from backend.services.llm_service import llm_service
from backend.config.settings import settings

logger = logging.getLogger(__name__)


class AgentTools:
    """Agent 工具集 - 所有工具方法接收 user_id 作为第一个参数，确保用户隔离"""

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
        # 只保留最近 20 次调用
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
    def _bm25_score(query_tokens: List[str], doc: str) -> float:
        """简易 BM25 关键词匹配评分"""
        doc_lower = doc.lower()
        score = 0.0
        for token in query_tokens:
            token_lower = token.lower()
            # 完全匹配加分多，部分匹配加分少
            if token_lower in doc_lower:
                score += 1.0
                # 统计出现次数
                score += doc_lower.count(token_lower) * 0.3
        return score

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """简易中文分词：提取中文字符和英文单词"""
        # 提取中文字符
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        # 提取英文单词
        english_words = re.findall(r'[a-zA-Z]+', text)
        return chinese_chars + english_words

    @staticmethod
    def search_knowledge(user_id: int, query: str, collection_name: Optional[str] = None,
                         n_results: int = 5, session_id: Optional[str] = None) -> str:
        """
        多路召回搜索用户知识库（BM25 + 语义检索）
        :param user_id: 用户ID
        :param query: 搜索关键词/问题
        :param collection_name: 可选的集合名称
        :param n_results: 返回结果数量
        :param session_id: 会话ID（用于工具调用追踪）
        :return: 检索到的知识文本
        """
        try:
            user_collection = AgentTools._get_user_collection(user_id, collection_name)

            # 1. 语义检索（向量相似度）- 失败时降级为纯 BM25
            semantic_results = None
            try:
                semantic_results = chroma_client.search(
                    collection_name=user_collection,
                    query_text=query,
                    n_results=n_results * 2,
                )
            except Exception as e:
                logger.warning(f"Semantic search failed, falling back to BM25 only: {e}")

            # 2. 获取集合中所有文档用于 BM25
            collection = chroma_client.get_or_create_collection(user_collection)
            all_docs = collection.get()

            # 3. BM25 关键词检索
            query_tokens = AgentTools._tokenize(query)
            bm25_scores = []
            if all_docs and all_docs.get("documents"):
                for i, doc in enumerate(all_docs["documents"]):
                    if doc:
                        score = AgentTools._bm25_score(query_tokens, doc)
                        bm25_scores.append({
                            "id": all_docs["ids"][i] if i < len(all_docs["ids"]) else str(i),
                            "doc": doc,
                            "score": score,
                            "metadata": all_docs["metadatas"][i] if all_docs.get("metadatas") and i < len(all_docs["metadatas"]) else {}
                        })

            # 按 BM25 分数排序，取前 n_results*2
            bm25_scores.sort(key=lambda x: x["score"], reverse=True)
            bm25_top = bm25_scores[:n_results * 2]

            # 4. 融合排序（RRF - Reciprocal Rank Fusion）
            fused_results = AgentTools._rrf_fusion(semantic_results, bm25_top, n_results)

            if not fused_results:
                result_text = "知识库中未找到相关内容。"
                if session_id:
                    AgentTools.record_tool_call(session_id, "search_knowledge",
                                                {"query": query, "collection": user_collection}, result_text)
                return result_text

            parts = []
            for i, item in enumerate(fused_results[:n_results]):
                source = item.get("metadata", {}).get("filename", f"文档{i+1}")
                parts.append(f"[来源: {source}]\n{item['doc']}")

            result_text = "\n\n---\n\n".join(parts)

            if session_id:
                AgentTools.record_tool_call(session_id, "search_knowledge",
                                            {"query": query, "collection": user_collection}, result_text)
            return result_text

        except Exception as e:
            logger.error(f"Search knowledge failed: {e}")
            error_msg = f"搜索知识库时出错: {str(e)}"
            if session_id:
                AgentTools.record_tool_call(session_id, "search_knowledge",
                                            {"query": query}, error_msg)
            return error_msg

    @staticmethod
    def _rrf_fusion(semantic_results: Optional[Dict], bm25_results: List[Dict], k: int = 60) -> List[Dict]:
        """RRF 融合排序：结合语义检索和 BM25 结果"""
        scores = {}

        # 语义检索排名得分
        if semantic_results and semantic_results.get("documents"):
            docs = semantic_results["documents"][0] if semantic_results["documents"] else []
            ids = semantic_results["ids"][0] if semantic_results.get("ids") else []
            metadatas = semantic_results.get("metadatas", [[]])[0] if semantic_results.get("metadatas") else []

            for rank, (doc_id, doc, meta) in enumerate(zip(ids, docs, metadatas)):
                if doc_id not in scores:
                    scores[doc_id] = {"doc": doc, "metadata": meta, "score": 0}
                scores[doc_id]["score"] += 1.0 / (k + rank + 1)

        # BM25 排名得分
        for rank, item in enumerate(bm25_results):
            doc_id = item["id"]
            if doc_id not in scores:
                scores[doc_id] = {"doc": item["doc"], "metadata": item["metadata"], "score": 0}
            scores[doc_id]["score"] += 1.0 / (k + rank + 1)

        # 按融合分数排序
        sorted_results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        return sorted_results

    @staticmethod
    def add_knowledge(user_id: int, text: str, collection_name: Optional[str] = None,
                      session_id: Optional[str] = None) -> str:
        """
        添加知识到用户知识库
        :param user_id: 用户ID
        :param text: 要添加的知识文本
        :param collection_name: 可选的集合名称
        :param session_id: 会话ID（用于工具调用追踪）
        :return: 添加结果
        """
        try:
            if not text or not text.strip():
                result = "错误：保存内容不能为空。请从历史对话中找到具体内容后再保存。"
                if session_id:
                    AgentTools.record_tool_call(session_id, "add_knowledge", {"text": text}, result)
                return result

            user_collection = AgentTools._get_user_collection(user_id, collection_name)
            item_id = str(uuid.uuid4())

            chroma_client.add_texts(
                collection_name=user_collection,
                texts=[text],
                metadatas=[{"user_id": str(user_id), "type": "manual_add"}],
                ids=[item_id],
            )
            result = f"知识已添加到知识库（collection: {user_collection}, id: {item_id}）"
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
        """
        查询改写：将用户的模糊/指代性查询改写为独立完整的查询
        :param original_query: 原始查询
        :param history: 历史对话（可选）
        :return: 改写后的查询
        """
        # 简单规则改写（后续可接入 LLM 做更智能的改写）
        query = original_query.strip()

        # 指代消解规则
        pronouns = ["这个", "那个", "刚才", "之前", "上面", "这些", "那些"]
        has_pronoun = any(p in query for p in pronouns)

        if has_pronoun and history:
            # 从历史中提取最近一条 assistant 回复的摘要
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    # 提取前 100 字作为上下文
                    context = content[:100] + "..." if len(content) > 100 else content
                    query = f"基于之前的讨论（{context}），用户问：{query}"
                    break

        # 保存意图识别
        save_keywords = ["保存", "记录", "存到", "存入", "加入知识库", "放进知识库"]
        if any(kw in query for kw in save_keywords):
            query = f"[保存意图] {query}"

        return query

    @staticmethod
    def calculator(expression: str, session_id: Optional[str] = None) -> str:
        """
        数学计算器
        :param expression: 数学表达式
        :param session_id: 会话ID（用于工具调用追踪）
        :return: 计算结果
        """
        try:
            allowed = set("0123456789+-*/.()^% ")
            if not all(c in allowed for c in expression):
                result = "错误：表达式包含非法字符。"
                if session_id:
                    AgentTools.record_tool_call(session_id, "calculator", {"expression": expression}, result)
                return result

            safe_expr = expression.replace("^", "**")
            result = eval(safe_expr, {"__builtins__": {}}, {})
            result_text = f"计算结果: {result}"
            if session_id:
                AgentTools.record_tool_call(session_id, "calculator", {"expression": expression}, result_text)
            return result_text
        except Exception as e:
            error_msg = f"计算错误: {str(e)}"
            if session_id:
                AgentTools.record_tool_call(session_id, "calculator", {"expression": expression}, error_msg)
            return error_msg

    @staticmethod
    def get_conversation_history(user_id: int, session_id: str, limit: int = 10) -> str:
        """
        获取对话历史
        :param user_id: 用户ID
        :param session_id: 会话ID
        :param limit: 返回最近几条记录
        :return: 格式化的对话历史
        """
        try:
            key = f"agent:history:{user_id}:{session_id}"
            history_raw = redis_client.client.lrange(key, -limit, -1)
            if not history_raw:
                return "暂无对话历史。"

            parts = []
            for item in history_raw:
                try:
                    msg = json.loads(item)
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    parts.append(f"[{role}] {content}")
                except:
                    continue

            return "\n".join(parts) if parts else "暂无对话历史。"
        except Exception as e:
            logger.error(f"Get history failed: {e}")
            return f"获取历史失败: {str(e)}"

    @staticmethod
    def get_used_tools(session_id: str) -> str:
        """
        获取当前会话已使用的工具列表
        :param session_id: 会话ID
        :return: 工具使用记录文本
        """
        calls = AgentTools.get_tool_calls(session_id)
        if not calls:
            return "本次对话中尚未使用任何工具。"

        parts = [f"本次对话已使用 {len(calls)} 个工具："]
        for i, call in enumerate(calls, 1):
            parts.append(f"{i}. {call['tool']}: {call['output'][:100]}...")
        return "\n".join(parts)

    @staticmethod
    def web_search_placeholder(query: str, session_id: Optional[str] = None) -> str:
        """
        联网搜索（占位实现）
        """
        result = (
            f"[联网搜索占位] 搜索关键词: '{query}'\n"
            "注意：当前未接入真实搜索引擎。"
        )
        if session_id:
            AgentTools.record_tool_call(session_id, "web_search_placeholder", {"query": query}, result)
        return result


# 工具描述，用于 Agent Prompt
TOOLS_DESCRIPTION = """
1. search_knowledge(user_id, query, collection_name=None, n_results=5)
   - 搜索用户知识库（自动使用BM25+语义多路召回）
   - 当用户问题可能与知识库有关时使用

2. add_knowledge(user_id, text, collection_name=None)
   - 将新知识添加到用户知识库
   - 当用户要求保存/记录信息时使用，text参数必须传入完整内容

3. calculator(expression)
   - 数学计算器
   - 当用户问数学问题或需要计算时使用

4. get_used_tools(session_id)
   - 查看本次对话已使用的工具列表
   - 当用户问"你用了什么工具"时使用

5. web_search_placeholder(query)
   - 联网搜索（占位实现）
   - 当知识库中没有答案且需要外部信息时使用
"""
