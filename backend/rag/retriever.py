"""
RAG 检索器模块 v2.0
集成 Multi-Query 查询改写、混合检索（语义+BM25）、RRF 融合排序、MMR 多样性重排。
提供同步和异步两种调用方式。
"""
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from backend.config.settings import settings
from backend.rag.enhanced_rag import HybridRetriever, QueryRewriter
import logging

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    RAG 检索器（增强版）
    支持 Multi-Query 改写 + 语义检索 + BM25 + RRF + MMR
    """

    def __init__(self, collection_name: str = "default"):
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-v3",
            openai_api_key=settings.DASHSCOPE_API_KEY,
            openai_api_base=settings.LLM_BASE_URL
        )
        self.collection_name = collection_name
        self.vectorstore = None
        self.hybrid_retriever = HybridRetriever()

    def load_vectorstore(self):
        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory="./chroma_db"
        )
        return self.vectorstore

    def retrieve(self, query: str, k: int = 3) -> list[Document]:
        """基础检索（兼容旧接口）"""
        if not self.vectorstore:
            self.load_vectorstore()
        return self.vectorstore.similarity_search(query, k=k)

    async def retrieve_enhanced(
        self,
        query: str,
        k: int = 5,
        use_multi_query: bool = True,
        use_hyde: bool = False,
        use_mmr: bool = True,
    ) -> dict:
        """
        增强检索：Multi-Query + 语义+BM25混合 + RRF融合 + MMR重排
        :param query: 用户查询
        :param k: 返回结果数
        :param use_multi_query: 是否使用 Multi-Query 改写
        :param use_hyde: 是否使用 HyDE 改写
        :param use_mmr: 是否使用 MMR 多样性重排
        :return: 检索结果字典
        """
        return await self.hybrid_retriever.retrieve(
            query=query,
            collection_name=self.collection_name,
            n_results=k,
            use_multi_query=use_multi_query,
            use_hyde=use_hyde,
            use_mmr=use_mmr,
        )

    def get_relevant_context(self, query: str, k: int = 3) -> str:
        """获取相关上下文（兼容旧接口）"""
        docs = self.retrieve(query, k=k)
        context = "\n\n".join([doc.page_content for doc in docs])
        return context


class RAGChain:
    """RAG 问答链"""

    SYSTEM_PROMPT = """
你是一名专业的大学课程答疑老师。请根据提供的参考知识来回答用户的问题。

参考知识：
{context}

回答要求：
1. 结合参考知识准确回答问题
2. 如果参考知识不足以回答，请明确说明
3. 解释清晰易懂，必要时提供示例
"""

    def __init__(self, collection_name: str = "default"):
        self.retriever = RAGRetriever(collection_name)

        from langchain_openai import ChatOpenAI
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0.4,
            timeout=settings.LLM_TIMEOUT
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("user", "问题：{question}")
        ])

    def invoke(self, question: str) -> str:
        context = self.retriever.get_relevant_context(question, k=3)

        chain = self.prompt | self.llm | StrOutputParser()

        return chain.invoke({
            "context": context,
            "question": question
        })


rag_chain = RAGChain()
