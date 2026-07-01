"""
ChromaDB 客户端封装
使用 HttpClient 连接独立的 ChromaDB 服务
v1.1: 添加 SSL 禁用配置，修复 SSL 握手错误
"""
import logging
import os
import uuid
from typing import List, Optional, Dict, Any

import chromadb
from chromadb.config import Settings

from backend.config.settings import settings

logger = logging.getLogger(__name__)

# 全局禁用 SSL 验证（解决 ChromaDB 嵌入模型下载时的 SSL 错误）
os.environ["PYTHONHTTPSVERIFY"] = "0"
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""


class ChromaClient:
    """ChromaDB 客户端封装"""

    def __init__(self):
        self._client: Optional[chromadb.HttpClient] = None

    def _get_client(self) -> chromadb.HttpClient:
        """懒加载获取 ChromaDB HttpClient"""
        if self._client is None:
            self._client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                ssl=False,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )
            logger.info(
                f"ChromaDB HttpClient connected: {settings.CHROMA_HOST}:{settings.CHROMA_PORT}"
            )
        return self._client

    def get_or_create_collection(self, collection_name: str):
        """获取或创建集合"""
        client = self._get_client()
        return client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_texts(
        self,
        collection_name: str,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        添加文本到集合
        :param collection_name: 集合名称
        :param texts: 文本列表
        :param metadatas: 元数据列表（可选）
        :param ids: ID 列表（可选，自动生成）
        :return: 实际使用的 ID 列表
        """
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]

        collection = self.get_or_create_collection(collection_name)
        collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info(
            f"Added {len(texts)} texts to collection '{collection_name}'"
        )
        return ids

    def search(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = 5,
    ) -> Dict[str, Any]:
        """
        搜索知识库
        :param collection_name: 集合名称
        :param query_text: 查询文本
        :param n_results: 返回结果数量
        :return: 搜索结果字典
        """
        collection = self.get_or_create_collection(collection_name)
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )
        logger.info(
            f"Searched collection '{collection_name}' for: {query_text[:50]}..."
        )
        return results

    def delete_collection(self, collection_name: str) -> None:
        """删除集合"""
        client = self._get_client()
        client.delete_collection(name=collection_name)
        logger.info(f"Deleted collection '{collection_name}'")

    def list_collections(self) -> List[str]:
        """列出所有集合名称"""
        client = self._get_client()
        collections = client.list_collections()
        return [c.name for c in collections]


# 全局 ChromaDB 客户端实例
chroma_client = ChromaClient()
