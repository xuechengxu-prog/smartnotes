"""
ReAct Agent 核心实现 v5.0
架构：ReAct Prompt + Function Calling + MCP

技术栈：
  - ReAct Prompt: System Prompt 引导 LLM 进行 Thought -> Action -> Observation 推理
  - Function Calling: LangGraph StateGraph + ToolNode + bind_tools() 原生工具调用
  - MCP: 通过 langchain-mcp-adapters 统一加载外部 MCP Server 工具

链路说明：
  1. 用户给出 query
  2. Agent 对 query 进行改写（指代消解、意图识别）
  3. 检测保存意图则直接调用 add_knowledge
  4. LangGraph 编排 LLM 推理 + 工具调用循环
  5. LLM 通过 Function Calling 原生选择和参数化工具
  6. ToolNode 统一执行本地工具和 MCP 工具
  7. 生成回答（必须标注来源）
"""
import json
import logging
import time
import uuid
from typing import Optional, List, Dict, Any, AsyncIterator

from langchain_core.messages import (
    HumanMessage, SystemMessage, AIMessage, ToolMessage
)
from langgraph.graph import MessagesState

from backend.services.llm_service import llm_service
from backend.common.redis_client import redis_client
from backend.agent_qa.tools import AgentTools, create_local_tools

logger = logging.getLogger(__name__)

# ReAct 风格 System Prompt，引导 LLM 进行推理-行动循环
REACT_SYSTEM_PROMPT = """你是SmartNotes智能学习助手，一个基于 ReAct（推理+行动）架构的智能 Agent。

【工作方式】
你会按照 Thought -> Action -> Observation -> Final Answer 的循环来思考和回答问题：
1. Thought: 分析用户问题，思考需要使用什么工具或信息
2. Action: 通过 Function Calling 调用合适的工具获取信息
3. Observation: 获取工具返回的结果
4. 重复上述步骤直到收集到足够信息
5. Final Answer: 综合所有信息生成最终回答

【工具使用规则】
- 回答用户问题前，必须先调用 search_knowledge 搜索知识库
- search_knowledge 支持 collection_name 参数指定知识库名称（如 "agent_memory"），不填则搜索用户所有知识库
- 如果搜索到相关内容，基于搜索结果回答；如果未找到，再使用自身知识回答
- 当用户说"保存"、"记录"、"存到知识库"时，调用 add_knowledge 工具
- add_knowledge 支持 collection_name 参数指定保存到哪个知识库，不填则使用默认知识库
- 可以使用联网搜索工具获取最新信息
- 可以使用学习辅助工具（闪卡、测验、摘要）帮助用户学习

【回答规范】
- 每个回答末尾必须加来源标注："📚 来源：您的知识库" 或 "📚 来源：模型自身知识"
- 只有 search_knowledge 成功找到内容时来源才是"您的知识库"
- 如果使用了联网搜索，标注："📚 来源：联网搜索"
- 回答应准确、有条理、有深度"""


class ReActAgent:
    """
    ReAct Agent v5.0 - Function Calling + MCP 架构
    """

    def __init__(self, user_id: int, session_id: Optional[str] = None,
                 mcp_tools: Optional[list] = None):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.mcp_tools = mcp_tools or []
        self.max_iterations = 8
        self.used_knowledge = False
        self.used_tools = []

        # 构建本地 Function Calling 工具
        self.local_tools = create_local_tools(self.user_id, self.session_id)

        # 合并所有工具（本地 + MCP）
        self.all_tools = self.local_tools + self.mcp_tools

        # 构建 LangGraph
        self._graph = self._build_graph()

    def _build_graph(self):
        """用 LangGraph StateGraph 构建 ReAct 推理循环"""
        from langgraph.graph import StateGraph, MessagesState, START, END
        from langgraph.prebuilt import ToolNode, tools_condition
        from langgraph.graph.message import add_messages

        tools = self.all_tools

        async def call_model(state: MessagesState):
            """调用 LLM，通过 bind_tools 启用 Function Calling"""
            messages = state["messages"]
            # 在消息列表前面插入 System Prompt
            system_msg = SystemMessage(content=REACT_SYSTEM_PROMPT)
            all_messages = [system_msg] + messages

            # bind_tools 将工具 schema 发送给 LLM，启用原生 Function Calling
            llm_with_tools = llm_service.llm.bind_tools(tools)
            response = await llm_with_tools.ainvoke(all_messages)
            return {"messages": response}

        # 构建状态图
        builder = StateGraph(MessagesState)

        # 添加节点
        builder.add_node("agent", call_model)
        builder.add_node("tools", ToolNode(tools))

        # 定义边：START -> agent -> (条件判断) -> tools 或 END
        builder.add_edge(START, "agent")
        builder.add_conditional_edges("agent", tools_condition)
        builder.add_edge("tools", "agent")

        return builder.compile()

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

    def _is_save_intent(self, question: str) -> bool:
        save_keywords = ["保存", "记录", "存到知识库", "存入知识库", "添加到知识库", "放进知识库"]
        return any(kw in question for kw in save_keywords)

    async def _rewrite_query(self, question: str, history: List[Dict[str, str]]) -> str:
        rewritten = AgentTools.query_rewrite(question, history)
        logger.info(f"Query rewrite: '{question}' -> '{rewritten}'")
        return rewritten

    async def _extract_content_for_save(self, history: List[Dict[str, str]]) -> str:
        if not history:
            return ""
        parts = []
        for i in range(len(history) - 1, -1, -1):
            msg = history[i]
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "assistant" and content and len(content) > 100:
                parts.append(f"问题：{history[i-1].get('content', '') if i > 0 else ''}\n\n回答：{content}")
                break
        if parts:
            return parts[0]
        for msg in history:
            if msg.get("role") == "assistant" and msg.get("content"):
                parts.append(msg.get("content"))
        return "\n\n---\n\n".join(parts) if parts else ""

    async def _build_messages_with_history(self, question: str, history: List[Dict[str, str]]) -> List:
        messages = []
        for msg in history:
            role = msg.get("role", "user")
            content = self._truncate_content(msg.get("content", ""), max_len=600)
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=question))
        return messages

    def _extract_answer_and_tools(self, state: MessagesState) -> tuple:
        """从 LangGraph 状态中提取最终回答和使用的工具列表"""
        messages = state.get("messages", [])
        used_tools = []
        knowledge_used = False

        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_name = tc.get("name", "unknown")
                    if tool_name not in used_tools:
                        used_tools.append(tool_name)
                    if tool_name == "search_knowledge":
                        knowledge_used = True
            elif isinstance(msg, ToolMessage):
                # 检查 search_knowledge 的返回是否包含有效内容
                if hasattr(msg, 'name') and msg.name == "search_knowledge":
                    content = msg.content if hasattr(msg, 'content') else str(msg)
                    if "未找到" not in content and "出错" not in content and len(content) > 50:
                        knowledge_used = True

        # 提取最终文本回答
        final_text = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
                final_text = msg.content
                break

        return final_text, used_tools, knowledge_used

    async def run(self, question: str) -> Dict[str, Any]:
        """完整链路运行（非流式）"""
        self.used_tools = []
        self.used_knowledge = False

        await self._save_message("user", question)

        # 强制处理保存意图
        if self._is_save_intent(question):
            return await self._handle_save_intent(question)

        # Step 1: Query改写
        history = await self._get_history(limit=10)
        rewritten_query = await self._rewrite_query(question, history)

        # Step 2-6: LangGraph 编排（Function Calling + MCP）
        messages = await self._build_messages_with_history(rewritten_query, history)

        try:
            config = {"recursion_limit": self.max_iterations}
            state = await self._graph.ainvoke({"messages": messages}, config=config)
        except Exception as e:
            logger.error(f"LangGraph execution failed: {e}")
            fallback = f"抱歉，处理您的问题时出现了错误：{str(e)}"
            await self._save_message("assistant", fallback)
            return {
                "answer": fallback + "\n\n📚 来源：模型自身知识",
                "thoughts": ["LangGraph 执行出错"],
                "actions": [],
                "used_tools": self.used_tools,
                "source": "llm",
                "session_id": self.session_id,
            }

        # 提取结果
        answer, used_tools, knowledge_used = self._extract_answer_and_tools(state)
        self.used_tools = used_tools
        self.used_knowledge = knowledge_used

        # 确保有来源标注
        if answer and "📚 来源" not in answer:
            if self.used_knowledge:
                answer += "\n\n📚 来源：您的知识库"
            else:
                answer += "\n\n📚 来源：模型自身知识"
        elif not answer:
            answer = "抱歉，我未能生成有效的回答。"

        await self._save_message("assistant", answer)

        # 提取 thought 过程（从 AIMessage 的 content 中）
        thoughts = []
        for msg in state.get("messages", []):
            if isinstance(msg, AIMessage) and msg.tool_calls and msg.content:
                thoughts.append(msg.content.strip())

        # 提取 actions 信息
        actions = []
        for msg in state.get("messages", []):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    actions.append({
                        "action": tc.get("name"),
                        "input": tc.get("args", {}),
                    })

        return {
            "answer": answer,
            "thoughts": thoughts,
            "actions": actions,
            "used_tools": self.used_tools,
            "source": "knowledge_base" if self.used_knowledge else "llm",
            "session_id": self.session_id,
        }

    async def _handle_save_intent(self, question: str) -> Dict[str, Any]:
        """处理保存意图"""
        history = await self._get_history(limit=10)
        content_to_save = await self._extract_content_for_save(history)
        if content_to_save:
            result = AgentTools.add_knowledge_impl(
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

    async def run_stream(self, question: str) -> AsyncIterator[Dict[str, Any]]:
        """完整链路运行（流式）"""
        self.used_tools = []
        self.used_knowledge = False

        await self._save_message("user", question)

        # 强制处理保存意图
        if self._is_save_intent(question):
            history = await self._get_history(limit=10)
            content_to_save = await self._extract_content_for_save(history)
            if content_to_save:
                yield {"type": "action", "content": "正在保存到知识库..."}
                result = AgentTools.add_knowledge_impl(
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
                       "used_tools": self.used_tools, "source": "llm"}
                await self._save_message("assistant", answer)
            else:
                answer = "未能从历史对话中找到可保存的内容。请先进行对话，再尝试保存。\n\n📚 来源：模型自身知识"
                yield {"type": "final_answer", "content": answer,
                       "used_tools": self.used_tools, "source": "llm"}
                await self._save_message("assistant", answer)
            return

        # Step 1: Query改写
        history = await self._get_history(limit=10)
        rewritten_query = await self._rewrite_query(question, history)

        # Step 2-6: LangGraph 流式执行
        messages = await self._build_messages_with_history(rewritten_query, history)

        try:
            config = {"recursion_limit": self.max_iterations}

            # 使用 astream 逐步获取事件
            async for event in self._graph.astream_events(
                {"messages": messages}, config=config, version="v2"
            ):
                event_type = event.get("event", "")

                # LLM 生成的 token（流式输出）
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield {"type": "token", "content": chunk.content}

                # 工具调用开始
                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    yield {"type": "action", "content": f"正在调用工具: {tool_name}"}
                    if tool_name not in self.used_tools:
                        self.used_tools.append(tool_name)
                    if tool_name == "search_knowledge":
                        self.used_knowledge = True

                # 工具返回结果
                elif event_type == "on_tool_end":
                    output = event.get("data", {}).get("output", "")
                    if output:
                        output_str = str(output)
                        yield {"type": "observation", "content": output_str[:500]}

        except Exception as e:
            logger.error(f"LangGraph stream failed: {e}")
            yield {"type": "final_answer",
                   "content": f"抱歉，处理您的问题时出现了错误：{str(e)}\n\n📚 来源：模型自身知识",
                   "used_tools": self.used_tools, "source": "llm"}
            return

        # 流式结束后，获取完整状态以提取最终回答
        try:
            state = await self._graph.ainvoke({"messages": messages}, config=config)
            answer, used_tools, knowledge_used = self._extract_answer_and_tools(state)
            self.used_tools = list(set(self.used_tools + used_tools))
            if knowledge_used:
                self.used_knowledge = True

            if answer and "📚 来源" not in answer:
                if self.used_knowledge:
                    answer += "\n\n📚 来源：您的知识库"
                else:
                    answer += "\n\n📚 来源：模型自身知识"
        except:
            answer = ""

        if answer:
            await self._save_message("assistant", answer)
            yield {"type": "final_answer", "content": answer,
                   "used_tools": self.used_tools,
                   "source": "knowledge_base" if self.used_knowledge else "llm"}
        else:
            # 从 token 流中可能已经发送了内容，这里不重复发送
            # 发送一个带来源标注的结束事件
            source = "knowledge_base" if self.used_knowledge else "llm"
            source_label = "您的知识库" if self.used_knowledge else "模型自身知识"
            yield {"type": "final_answer",
                   "content": f"\n\n📚 来源：{source_label}",
                   "used_tools": self.used_tools, "source": source}


async def create_agent(user_id: int, session_id: Optional[str] = None,
                        mcp_tools: Optional[list] = None) -> ReActAgent:
    return ReActAgent(user_id=user_id, session_id=session_id, mcp_tools=mcp_tools)
