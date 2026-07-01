"""
LangChain 笔记整理链
使用 LLM 将原始笔记内容整理为结构化的学习笔记
"""
import logging
from typing import AsyncIterator, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.services.llm_service import llm_service

logger = logging.getLogger(__name__)


# 笔记整理系统提示词
NOTE_SYSTEM_PROMPT = """你是一位专业的学习笔记整理助手。你的任务是将用户提供的原始笔记内容整理为结构清晰、重点突出的学习笔记。

整理要求：
1. 提取核心概念和关键知识点
2. 使用层级标题组织内容（# 一级标题, ## 二级标题, ### 三级标题）
3. 对重要内容使用加粗标记
4. 将列表内容整理为有序或无序列表
5. 添加适当的总结和归纳
6. 保持内容的准确性和完整性
7. 使用 Markdown 格式输出

输出格式：
- 开头简要概述笔记主题
- 主体部分按知识点分层展开
- 结尾提供关键要点总结
"""

NOTE_HUMAN_TEMPLATE = """请帮我整理以下笔记内容：

原始笔记：
{content}

{style_hint}
"""


class NoteChain:
    """笔记整理 LangChain 链"""

    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", NOTE_SYSTEM_PROMPT),
            ("human", NOTE_HUMAN_TEMPLATE),
        ])
        self.output_parser = StrOutputParser()
        # 构建链: prompt -> llm -> parser
        self.chain = self.prompt | llm_service.llm | self.output_parser

    async def organize(
        self,
        content: str,
        style: Optional[str] = None,
    ) -> str:
        """
        整理笔记（非流式）
        :param content: 原始笔记内容
        :param style: 整理风格提示（可选）
        :return: 整理后的笔记
        """
        style_hint = f"整理风格要求：{style}" if style else ""
        logger.info(f"Organizing note, content length: {len(content)}")

        result = await self.chain.ainvoke({
            "content": content,
            "style_hint": style_hint,
        })
        return result

    async def organize_stream(
        self,
        content: str,
        style: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        整理笔记（流式输出）
        :param content: 原始笔记内容
        :param style: 整理风格提示（可选）
        :yield: 流式文本片段
        """
        style_hint = f"整理风格要求：{style}" if style else ""
        logger.info(f"Organizing note (stream), content length: {len(content)}")

        async for chunk in self.chain.astream({
            "content": content,
            "style_hint": style_hint,
        }):
            yield chunk


# 全局链实例
note_chain = NoteChain()
