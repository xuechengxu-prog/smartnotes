"""
ReAct Agent 核心实现 v4.0
完整链路：Query改写 -> 工具选择 -> 多路召回 -> 生成回答 -> 历史查询

链路说明：
  1. 用户给出 query
  2. Agent 对 query 进行改写（指代消解、意图识别）
  3. LLM 根据改写后的 query 选择调用哪个 tool
  4. 调用 tool 同时检索知识库（BM25 + 语义多路召回）
  5. 将召回内容与 query 同时发给 LLM
  6. LLM 根据 prompt 生成回答（必须标注来源）
  7. 用户问"是否基于知识库"、"用了哪些工具"、"保存到知识库"等问题
  8. LLM 查询历史对话并参考历史给出回复或执行操作
"""
import json
import logging
import re
import time
import uuid
from typing import Optional, List, Dict, Any, AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from backend.services.llm_service import llm_service
from backend.common.redis_client import redis_client
from backend.agent_qa.tools import AgentTools, TOOLS_DESCRIPTION

logger = logging.getLogger(__name__)


class ReActAgent:
    """
    ReAct Agent v4.0 - 完整RAG链路实现
    """

    TOOLS = {
        "search_knowledge": AgentTools.search_knowledge,
        "add_knowledge": AgentTools.add_knowledge,
        "calculator": AgentTools.calculator,
        "get_used_tools": AgentTools.get_used_tools,
        "web_search_placeholder": AgentTools.web_search_placeholder,
    }

    def __init__(self, user_id: int, session_id: Optional[str] = None):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.max_iterations = 8
        # 记录本次对话是否使用了知识库
        self.used_knowledge = False
        # 记录本次对话使用的工具
        self.used_tools = []

    def _build_system_prompt(self) -> str:
        return f"""你是SmartNotes智能学习助手。用户ID={self.user_id}，会话ID={self.session_id}。

可用工具：
{TOOLS_DESCRIPTION}

【强制规则】
规则1（记忆）：对话历史已自动注入。请仔细阅读历史消息理解用户意图。
规则2（搜索优先）：回答用户问题前，必须先调用search_knowledge搜索知识库。如果搜索到相关内容，基于搜索结果回答；如果未找到，再使用自身知识回答。
规则3（保存到知识库）：当用户说"保存"、"记录"、"存到知识库"时，你必须调用add_knowledge工具。text参数必须包含完整的内容（至少100字），可以从历史对话中提取AI的回答内容。
规则4（工具查询）：当用户问"你用了什么工具"、"你调用了哪些工具"时，调用get_used_tools查询并如实回答。
规则5（来源标注）：每个Final Answer末尾必须加："📚 来源：您的知识库" 或 "📚 来源：模型自身知识"。只有search_knowledge成功找到内容时来源才是"您的知识库"。

输出格式：
Thought: 你的思考
Action: 工具名
Action Input: {{"参数": "值"}}
Observation: [工具返回，系统自动填充]
...
Final Answer: 回答（末尾加来源标注）
"""

    async def _get_history(self, limit: int = 10) -> List[Dict[str, str]]:
        try:
            key = f"agent:history:{self.user_id}:{self.session_id}"
            history_raw = await redis_client.client.lrange(key, -limit, -1)
            history = []
            for item in history_raw:
                try:
                    msg = json.loads(item)
                    history.append(msg)
                except:
                    continue
            return history
        except Exception as e:
            logger.error(f"Get history failed: {e}")
            return []

    async def _save_message(self, role: str, content: str):
        try:
            key = f"agent:history:{self.user_id}:{self.session_id}"
            msg = {"role": role, "content": content, "timestamp": str(uuid.uuid4())}
            await redis_client.client.rpush(key, json.dumps(msg, ensure_ascii=False))
            await redis_client.client.ltrim(key, -50, -1)
            await redis_client.client.expire(key, 604800)

            # 更新 session meta（记录 updated_at 时间戳）
            meta_key = f"agent:session_meta:{self.user_id}:{self.session_id}"
            meta = {"updated_at": str(time.time()), "session_id": self.session_id}
            await redis_client.client.hset(meta_key, mapping=meta)
            await redis_client.client.expire(meta_key, 604800)
        except Exception as e:
            logger.error(f"Save message failed: {e}")

    def _truncate_content(self, content: str, max_len: int = 600) -> str:
        if len(content) <= max_len:
            return content
        truncated = content[:max_len]
        last_period = max(truncated.rfind('。'), truncated.rfind('.'), truncated.rfind('\n'))
        if last_period > max_len * 0.7:
            truncated = truncated[:last_period + 1]
        return truncated + "\n[...内容已截断]"

    def _parse_action(self, text: str) -> Optional[Dict[str, Any]]:
        action_match = re.search(r"Action:\s*(\w+)", text, re.IGNORECASE)
        if not action_match:
            return None
        action_name = action_match.group(1).strip()

        input_match = re.search(r"Action Input:\s*(\{.*?\})\s*(?:\n|$)", text, re.DOTALL)
        if input_match:
            try:
                action_input = json.loads(input_match.group(1))
                return {"action": action_name, "input": action_input}
            except json.JSONDecodeError:
                return {"action": action_name, "input": {"query": input_match.group(1).strip()}}

        func_match = re.search(rf"Action:\s*{action_name}\s*\((.*?)\)", text, re.DOTALL)
        if func_match:
            try:
                action_input = json.loads("{" + func_match.group(1) + "}")
                return {"action": action_name, "input": action_input}
            except:
                return {"action": action_name, "input": {"query": func_match.group(1).strip()}}

        return {"action": action_name, "input": {}}

    def _has_final_answer(self, text: str) -> bool:
        return bool(re.search(r"Final Answer:", text, re.IGNORECASE))

    def _extract_final_answer(self, text: str) -> str:
        match = re.search(r"Final Answer:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _extract_thought(self, text: str) -> Optional[str]:
        match = re.search(r"Thought:\s*(.*?)(?:\nAction:|\nFinal Answer:|$)", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    async def _call_tool(self, action_name: str, action_input: Dict[str, Any]) -> str:
        if action_name not in self.TOOLS:
            return f"错误：未知工具 '{action_name}'"

        tool_func = self.TOOLS[action_name]

        # 自动注入必要参数
        if "user_id" not in action_input:
            action_input["user_id"] = self.user_id
        if "session_id" not in action_input:
            action_input["session_id"] = self.session_id

        # 特殊处理：add_knowledge 时如果 text 为空或太短，自动从历史中提取
        if action_name == "add_knowledge":
            text = action_input.get("text", "")
            if not text or len(text.strip()) < 50:
                logger.warning(f"add_knowledge text too short ({len(text) if text else 0} chars), extracting from history")
                history = await self._get_history(limit=10)
                extracted = self._extract_content_for_save(history)
                if extracted:
                    action_input["text"] = extracted
                    logger.info(f"Extracted content for save: {len(extracted)} chars")
                else:
                    return "错误：无法从历史对话中提取有效内容。请确保对话中有足够的信息可供保存。"

        try:
            result = tool_func(**action_input)
            # 记录工具使用
            if action_name not in self.used_tools:
                self.used_tools.append(action_name)
            # 只有 search_knowledge 成功找到内容时才标记 used_knowledge
            if action_name == "search_knowledge" and "未找到" not in result and "出错" not in result and len(result) > 50:
                self.used_knowledge = True
            return str(result)
        except Exception as e:
            logger.error(f"Tool {action_name} failed: {e}")
            return f"工具调用失败: {str(e)}"

    def _extract_content_for_save(self, history: List[Dict[str, str]]) -> str:
        """从历史对话中提取可用于保存到知识库的完整内容"""
        if not history:
            return ""

        parts = []
        # 提取最近一轮完整的 QA（用户问题 + AI 回答）
        for i in range(len(history) - 1, -1, -1):
            msg = history[i]
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "assistant" and content and len(content) > 100:
                # 找到 assistant 的详细回答，往前找对应的 user 问题
                parts.append(f"问题：{history[i-1].get('content', '') if i > 0 else ''}\n\n回答：{content}")
                break

        if parts:
            return parts[0]

        #  fallback：提取所有 assistant 的回复拼接
        for msg in history:
            if msg.get("role") == "assistant" and msg.get("content"):
                parts.append(msg.get("content"))

        return "\n\n---\n\n".join(parts) if parts else ""

    def _build_messages_with_history(self, question: str, history: List[Dict[str, str]]) -> List:
        messages = [SystemMessage(content=self._build_system_prompt())]

        for msg in history:
            role = msg.get("role", "user")
            content = self._truncate_content(msg.get("content", ""), max_len=600)
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=f"用户当前问题: {question}\n\n请按ReAct格式思考并回答。"))
        return messages

    async def _rewrite_query(self, question: str, history: List[Dict[str, str]]) -> str:
        """Step 1: Query改写"""
        rewritten = AgentTools.query_rewrite(question, history)
        logger.info(f"Query rewrite: '{question}' -> '{rewritten}'")
        return rewritten

    async def run(self, question: str) -> Dict[str, Any]:
        """
        完整链路运行（非流式）
        返回包含 answer, thoughts, actions, used_tools, source, session_id
        """
        thoughts = []
        actions = []
        self.used_tools = []
        self.used_knowledge = False

        # 保存用户问题
        await self._save_message("user", question)

        # 强制处理保存意图：直接调用 add_knowledge，不经过 LLM 判断
        if self._is_save_intent(question):
            history = await self._get_history(limit=10)
            content_to_save = self._extract_content_for_save(history)
            if content_to_save:
                result = AgentTools.add_knowledge(
                    user_id=self.user_id,
                    text=content_to_save,
                    session_id=self.session_id
                )
                if "已添加" in result or "成功" in result:
                    self.used_tools.append("add_knowledge")
                    answer = f"已将内容保存到知识库中。\n\n📚 来源：模型自身知识"
                else:
                    answer = f"保存时出现问题：{result}\n\n📚 来源：模型自身知识"
                await self._save_message("assistant", answer)
                return {
                    "answer": answer,
                    "thoughts": ["检测到保存意图，直接调用add_knowledge"],
                    "actions": [{"action": "add_knowledge", "input": {"text": content_to_save[:50] + "..."}}],
                    "used_tools": self.used_tools,
                    "source": "llm",
                    "session_id": self.session_id,
                }
            else:
                answer = "未能从历史对话中找到可保存的内容。请先进行对话，再尝试保存。\n\n📚 来源：模型自身知识"
                await self._save_message("assistant", answer)
                return {
                    "answer": answer,
                    "thoughts": ["检测到保存意图但无内容可保存"],
                    "actions": [],
                    "used_tools": self.used_tools,
                    "source": "llm",
                    "session_id": self.session_id,
                }

        # Step 1: Query改写
        history = await self._get_history(limit=10)
        rewritten_query = await self._rewrite_query(question, history)

        # Step 2-6: ReAct循环（工具选择 -> 多路召回 -> 生成回答）
        messages = self._build_messages_with_history(rewritten_query, history)

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            response = await llm_service.llm.ainvoke(messages)
            response_text = response.content

            thought = self._extract_thought(response_text)
            if thought:
                thoughts.append(thought)

            if self._has_final_answer(response_text):
                final_answer = self._extract_final_answer(response_text)

                # 确保有来源标注
                if "📚 来源" not in final_answer:
                    if self.used_knowledge:
                        final_answer += "\n\n📚 来源：您的知识库"
                    else:
                        final_answer += "\n\n📚 来源：模型自身知识"

                await self._save_message("assistant", final_answer)
                return {
                    "answer": final_answer,
                    "thoughts": thoughts,
                    "actions": actions,
                    "used_tools": self.used_tools,
                    "source": "knowledge_base" if self.used_knowledge else "llm",
                    "session_id": self.session_id,
                }

            action_info = self._parse_action(response_text)
            if action_info:
                actions.append(action_info)
                action_name = action_info["action"]
                action_input = action_info["input"]

                observation = await self._call_tool(action_name, action_input)

                messages.append(AIMessage(content=response_text))
                messages.append(HumanMessage(content=f"Observation: {observation}\n\n请继续思考。"))
            else:
                # 没有Action也没有Final Answer
                if "📚 来源" not in response_text:
                    if self.used_knowledge:
                        response_text += "\n\n📚 来源：您的知识库"
                    else:
                        response_text += "\n\n📚 来源：模型自身知识"

                await self._save_message("assistant", response_text)
                return {
                    "answer": response_text,
                    "thoughts": thoughts,
                    "actions": actions,
                    "used_tools": self.used_tools,
                    "source": "knowledge_base" if self.used_knowledge else "llm",
                    "session_id": self.session_id,
                }

        fallback = "抱歉，我尝试了多次但未能找到满意的答案。"
        if self.used_knowledge:
            fallback += "\n\n📚 来源：您的知识库"
        else:
            fallback += "\n\n📚 来源：模型自身知识"
        await self._save_message("assistant", fallback)
        return {
            "answer": fallback,
            "thoughts": thoughts,
            "actions": actions,
            "used_tools": self.used_tools,
            "source": "knowledge_base" if self.used_knowledge else "llm",
            "session_id": self.session_id,
        }

    def _is_save_intent(self, question: str) -> bool:
        """检测用户是否有保存到知识库的意图"""
        save_keywords = ["保存", "记录", "存到知识库", "存入知识库", "添加到知识库", "放进知识库"]
        return any(kw in question for kw in save_keywords)

    async def run_stream(self, question: str) -> AsyncIterator[Dict[str, Any]]:
        """
        完整链路运行（流式）
        yield包含 type, content, 以及可选的 used_tools, source
        """
        self.used_tools = []
        self.used_knowledge = False

        await self._save_message("user", question)

        # 强制处理保存意图：直接调用 add_knowledge，不经过 LLM 判断
        if self._is_save_intent(question):
            history = await self._get_history(limit=10)
            content_to_save = self._extract_content_for_save(history)
            if content_to_save:
                yield {"type": "action", "content": "正在保存到知识库..."}
                result = AgentTools.add_knowledge(
                    user_id=self.user_id,
                    text=content_to_save,
                    session_id=self.session_id
                )
                if "已添加" in result or "成功" in result:
                    self.used_tools.append("add_knowledge")
                    answer = f"已将内容保存到知识库中。\n\n📚 来源：模型自身知识"
                else:
                    answer = f"保存时出现问题：{result}\n\n📚 来源：模型自身知识"
                yield {"type": "final_answer", "content": answer,
                       "used_tools": self.used_tools,
                       "source": "llm"}
                await self._save_message("assistant", answer)
                return
            else:
                answer = "未能从历史对话中找到可保存的内容。请先进行对话，再尝试保存。\n\n📚 来源：模型自身知识"
                yield {"type": "final_answer", "content": answer,
                       "used_tools": self.used_tools,
                       "source": "llm"}
                await self._save_message("assistant", answer)
                return

        # Step 1: Query改写
        history = await self._get_history(limit=10)
        rewritten_query = await self._rewrite_query(question, history)

        messages = self._build_messages_with_history(rewritten_query, history)

        iteration = 0
        thought_yielded = False

        while iteration < self.max_iterations:
            iteration += 1

            buffer = ""
            async for chunk in llm_service.llm.astream(messages):
                text = chunk.content
                if text:
                    buffer += text
                    yield {"type": "token", "content": text}

            response_text = buffer

            if not thought_yielded:
                thought = self._extract_thought(response_text)
                if thought:
                    yield {"type": "thought", "content": thought}
                    thought_yielded = True

            if self._has_final_answer(response_text):
                final_answer = self._extract_final_answer(response_text)

                # 确保有来源标注
                if "📚 来源" not in final_answer:
                    if self.used_knowledge:
                        final_answer += "\n\n📚 来源：您的知识库"
                    else:
                        final_answer += "\n\n📚 来源：模型自身知识"

                yield {"type": "final_answer", "content": final_answer,
                       "used_tools": self.used_tools,
                       "source": "knowledge_base" if self.used_knowledge else "llm"}
                await self._save_message("assistant", final_answer)
                return

            action_info = self._parse_action(response_text)
            if action_info:
                yield {"type": "action", "content": f"正在调用工具: {action_info['action']}"}

                action_name = action_info["action"]
                action_input = action_info["input"]

                observation = await self._call_tool(action_name, action_input)
                yield {"type": "observation", "content": observation}

                messages.append(AIMessage(content=response_text))
                messages.append(HumanMessage(content=f"Observation: {observation}\n\n请继续思考。"))
            else:
                if "📚 来源" not in response_text:
                    if self.used_knowledge:
                        response_text += "\n\n📚 来源：您的知识库"
                    else:
                        response_text += "\n\n📚 来源：模型自身知识"

                yield {"type": "final_answer", "content": response_text,
                       "used_tools": self.used_tools,
                       "source": "knowledge_base" if self.used_knowledge else "llm"}
                await self._save_message("assistant", response_text)
                return

        fallback = "抱歉，我尝试了多次但未能找到满意的答案。"
        if self.used_knowledge:
            fallback += "\n\n📚 来源：您的知识库"
        else:
            fallback += "\n\n📚 来源：模型自身知识"
        yield {"type": "final_answer", "content": fallback,
               "used_tools": self.used_tools,
               "source": "knowledge_base" if self.used_knowledge else "llm"}
        await self._save_message("assistant", fallback)


async def create_agent(user_id: int, session_id: Optional[str] = None) -> ReActAgent:
    return ReActAgent(user_id=user_id, session_id=session_id)
