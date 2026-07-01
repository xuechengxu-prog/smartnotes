"""
LangChain 问答链
使用 LLM 回答用户问题，支持知识库 RAG 检索增强
"""
import logging
from typing import AsyncIterator

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class QAChain:
    """问答 LangChain 链，支持 RAG"""

    def __init__(self):
        self.llm = LLMService().get_llm()
        # RAG 检索提示词模板
        self.rag_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个智能学习助手。请根据以下检索到的知识库内容来回答用户的问题。
如果知识库中没有相关内容，请根据你的知识回答，但请注明"此回答未基于知识库内容"。

检索到的相关文档：
{context}

请用清晰、结构化的方式回答问题。"""),
            ("user", "{question}")
        ])
        # 普通问答提示词（无知识库内容时）
        self.normal_prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一个智能学习助手。请用清晰、结构化的方式回答学生的问题。"),
            ("user", "{question}")
        ])

    async def answer_stream(self, question: str, context: str = "") -> AsyncIterator[str]:
        """流式回答问题，支持 RAG"""
        if context:
            chain = self.rag_prompt | self.llm | StrOutputParser()
            async for chunk in chain.astream({"question": question, "context": context}):
                yield chunk
        else:
            chain = self.normal_prompt | self.llm | StrOutputParser()
            async for chunk in chain.astream({"question": question}):
                yield chunk


# 全局链实例
qa_chain = QAChain()
