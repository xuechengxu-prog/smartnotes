"""
文档加载与预处理模块 v2.0
集成了企业级数据清洗和中文智能切片能力。
使用 DataCleaner + SmartChunker 确保入库文档质量。
"""
from langchain_core.documents import Document
from backend.config.settings import settings
from backend.rag.enhanced_rag import DataCleaner, SmartChunker
import logging

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """文档处理器：加载 -> 清洗 -> 切片 -> 向量化"""

    def __init__(self):
        self.chunker = SmartChunker(
            chunk_size=500,
            chunk_overlap=50,
        )

    def load_document(self, file_path: str) -> list[Document]:
        """
        加载文档（支持 .txt / .md / .pdf）
        加载后自动执行数据清洗
        """
        if file_path.endswith('.pdf'):
            loader = PyPDFLoader(file_path)
        else:
            loader = TextLoader(file_path)
        docs = loader.load()
        # 自动清洗每个文档
        for doc in docs:
            doc.page_content = DataCleaner.clean_text(doc.page_content)
        return docs

    def process_raw_text(
        self,
        text: str,
        source: str = "",
        metadata: dict = None,
    ) -> tuple[list[str], list[dict], list[str]]:
        """
        处理原始文本：清洗 -> 切片，返回可直接入库的 chunks
        :param text: 原始文本
        :param source: 来源标识
        :param metadata: 额外元数据
        :return: (chunk_texts, chunk_metadatas, chunk_ids)
        """
        import uuid

        # Step 1: 数据清洗
        cleaned = DataCleaner.clean_text(text)
        if not cleaned.strip():
            return [], [], []

        # Step 2: 智能切片
        meta = {"source": source, **(metadata or {})}
        chunk_texts, chunk_metadatas = self.chunker.chunk_documents(
            [cleaned], [meta]
        )

        # Step 3: 生成唯一 ID
        chunk_ids = [str(uuid.uuid4()) for _ in chunk_texts]

        logger.info(
            f"文档处理完成: source='{source}', "
            f"清洗后 {len(cleaned)} 字 -> {len(chunk_texts)} 个 chunk"
        )
        return chunk_texts, chunk_metadatas, chunk_ids

    def create_vectorstore(self, documents: list[Document], collection_name: str):
        """
        从 Document 列表创建向量库（兼容旧接口）
        注意：推荐使用 process_raw_text + chroma_client.add_texts 代替
        """
        from langchain_openai import OpenAIEmbeddings
        from langchain_chroma import Chroma

        embeddings = OpenAIEmbeddings(
            model="text-embedding-v3",
            openai_api_key=settings.DASHSCOPE_API_KEY,
            openai_api_base=settings.LLM_BASE_URL
        )
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            collection_name=collection_name,
            persist_directory="./chroma_db"
        )
        return vectorstore


# 全局实例
document_processor = DocumentProcessor()
