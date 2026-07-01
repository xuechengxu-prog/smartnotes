"""
统一的 LLM 服务封装
基于 LangChain，使用百炼 qwen3.7-plus
"""
import logging
from typing import AsyncIterator, Optional, List, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

from backend.config.settings import settings

logger = logging.getLogger(__name__)


class LLMService:
    """统一 LLM 服务"""

    _instance: Optional["LLMService"] = None
    _llm: Optional[ChatOpenAI] = None

    def __new__(cls) -> "LLMService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def llm(self) -> ChatOpenAI:
        """获取 LLM 实例（懒加载）"""
        if self._llm is None:
            if not settings.DASHSCOPE_API_KEY:
                raise ValueError("DASHSCOPE_API_KEY 未设置")

            self._llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.DASHSCOPE_API_KEY,
                base_url=settings.LLM_BASE_URL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=settings.LLM_TIMEOUT,
                streaming=True,
            )
            logger.info(f"LLM initialized with model: {settings.LLM_MODEL}")
        return self._llm

    def get_llm(self, **kwargs) -> ChatOpenAI:
        """
        获取自定义参数的 LLM 实例
        :param kwargs: 覆盖默认参数
        """
        return ChatOpenAI(
            model=kwargs.get("model", settings.LLM_MODEL),
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=kwargs.get("temperature", settings.LLM_TEMPERATURE),
            max_tokens=kwargs.get("max_tokens", settings.LLM_MAX_TOKENS),
            timeout=kwargs.get("timeout", settings.LLM_TIMEOUT),
            streaming=kwargs.get("streaming", True),
        )

    async def ainvoke(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        异步调用 LLM（非流式）
        :param messages: 消息列表 [{"role": "user", "content": "..."}]
        :param system_prompt: 系统提示词
        :return: LLM 回复文本
        """
        lc_messages = []
        if system_prompt:
            lc_messages.append(SystemMessage(content=system_prompt))

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            elif role == "system":
                lc_messages.append(SystemMessage(content=content))

        response = await self.llm.ainvoke(lc_messages)
        return response.content

    async def astream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        异步流式调用 LLM
        :param messages: 消息列表
        :param system_prompt: 系统提示词
        :yield: 流式文本片段
        """
        lc_messages = []
        if system_prompt:
            lc_messages.append(SystemMessage(content=system_prompt))

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            elif role == "system":
                lc_messages.append(SystemMessage(content=content))

        async for chunk in self.llm.astream(lc_messages):
            if chunk.content:
                yield chunk.content

    def create_prompt_template(
        self,
        system_template: str,
        human_template: str,
    ) -> ChatPromptTemplate:
        """
        创建提示词模板
        :param system_template: 系统提示模板
        :param human_template: 用户提示模板
        :return: ChatPromptTemplate
        """
        return ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("human", human_template),
        ])

    async def invoke_chain(
        self,
        prompt_template: ChatPromptTemplate,
        variables: Dict[str, Any],
    ) -> str:
        """
        执行 LangChain 链
        :param prompt_template: 提示词模板
        :param variables: 模板变量
        :return: 链执行结果
        """
        chain = prompt_template | self.llm
        response = await chain.ainvoke(variables)
        return response.content

    async def stream_chain(
        self,
        prompt_template: ChatPromptTemplate,
        variables: Dict[str, Any],
    ) -> AsyncIterator[str]:
        """
        流式执行 LangChain 链
        :param prompt_template: 提示词模板
        :param variables: 模板变量
        :yield: 流式文本片段
        """
        chain = prompt_template | self.llm
        async for chunk in chain.astream(variables):
            if chunk.content:
                yield chunk.content


# 全局 LLM 服务实例
llm_service = LLMService()
