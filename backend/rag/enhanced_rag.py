"""
企业级 RAG 增强模块
提供查询改写、数据清洗、智能切片、混合检索、文档去重等能力，
用于提升知识库问答系统的检索质量和生成效果。

组件说明：
- QueryRewriter: 查询改写器（Multi-Query / HyDE / Step-Back）
- DataCleaner: 企业级文档数据清洗器
- SmartChunker: 中文优化的智能文本切片器
- HybridRetriever: 语义+BM25+RRF融合的混合检索器
- merge_and_deduplicate_results: 多查询结果去重合并
"""

import logging
import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

from backend.common.chroma_client import chroma_client
from backend.config.settings import settings
from backend.services.llm_service import llm_service

logger = logging.getLogger(__name__)


# ===========================================================================
# 1. QueryRewriter 查询改写器
# ===========================================================================

class QueryRewriter:
    """
    查询改写器
    通过 Multi-Query、HyDE、Step-Back 三种策略将用户原始问题改写为更利于检索的形式，
    从而提升向量检索的召回率和准确率。
    """

    # Multi-Query 改写提示词模板
    _MULTI_QUERY_TEMPLATE = """你是一个 AI 语言模型助手。你的任务是生成给定用户问题的 3 个不同版本，用于从向量数据库中检索相关文档。通过从多个角度生成用户问题，帮助克服相似度搜索的局限性。请用换行符分隔这些替代问题，不要编号。原始问题是: {question}"""

    # HyDE 改写提示词模板
    _HYDE_TEMPLATE = """请针对以下问题，写一段可能的回答文档。假设你拥有相关知识，请生成一个详尽、专业的假设性答案。该答案将用于在向量数据库中进行相似度检索。原始问题是: {question}"""

    # Step-Back 改写提示词模板
    _STEP_BACK_TEMPLATE = """请将以下具体问题抽象为一个更高层次、更宽泛的问题。目标是帮助检索到更广泛的背景知识。只输出改写后的高层次问题，不要解释。原始问题是: {question}"""

    @staticmethod
    async def multi_query_rewrite(query: str) -> List[str]:
        """
        Multi-Query 改写（异步版本）：将原始问题改写为 3-5 个不同角度的子查询。

        :param query: 用户原始查询
        :return: 包含原始查询和改写子查询的列表（3~5 个）
        """
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("human", QueryRewriter._MULTI_QUERY_TEMPLATE),
            ])
            chain = prompt | llm_service.llm | StrOutputParser()
            response = await chain.ainvoke({"question": query})

            rewritten = [line.strip() for line in response.strip().split("\n") if line.strip()]
            queries = [query] + rewritten
            queries = queries[:5]
            logger.info(f"Multi-Query 改写完成，生成 {len(queries)} 个子查询")
            return queries
        except Exception as e:
            logger.error(f"Multi-Query 改写失败: {e}")
            return [query]

    @staticmethod
    def multi_query_rewrite_sync(query: str) -> List[str]:
        """
        Multi-Query 改写（同步版本）：用于同步调用场景。

        :param query: 用户原始查询
        :return: 包含原始查询和改写子查询的列表（3~5 个）
        """
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("human", QueryRewriter._MULTI_QUERY_TEMPLATE),
            ])
            chain = prompt | llm_service.llm | StrOutputParser()
            response = chain.invoke({"question": query})

            rewritten = [line.strip() for line in response.strip().split("\n") if line.strip()]
            queries = [query] + rewritten
            queries = queries[:5]
            logger.info(f"Multi-Query 改写完成，生成 {len(queries)} 个子查询")
            return queries
        except Exception as e:
            logger.error(f"Multi-Query 改写失败: {e}")
            return [query]

    @staticmethod
    async def hyde_rewrite(query: str) -> str:
        """
        HyDE（Hypothetical Document Embedding）改写：
        用 LLM 生成假设性答案文档，使该假设文档的向量表示接近真实相关文档，
        从而克服查询与文档之间的语义鸿沟。

        :param query: 用户原始查询
        :return: LLM 生成的假设性答案文档文本
        """
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("human", QueryRewriter._HYDE_TEMPLATE),
            ])
            chain = prompt | llm_service.llm | StrOutputParser()
            response = await chain.ainvoke({"question": query})

            hypo_doc = response.strip()
            logger.info(f"HyDE 改写完成，假设文档长度: {len(hypo_doc)}")
            return hypo_doc
        except Exception as e:
            logger.error(f"HyDE 改写失败: {e}")
            return query

    @staticmethod
    async def step_back_rewrite(query: str) -> str:
        """
        Step-Back 提问改写：
        将具体的低层次问题抽象为高层次的背景问题，
        帮助检索到更广泛的上游知识以辅助推理。

        :param query: 用户原始查询
        :return: 抽象后的高层次问题
        """
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("human", QueryRewriter._STEP_BACK_TEMPLATE),
            ])
            chain = prompt | llm_service.llm | StrOutputParser()
            response = await chain.ainvoke({"question": query})

            abstract_q = response.strip()
            logger.info(f"Step-Back 改写完成: '{query}' -> '{abstract_q}'")
            return abstract_q
        except Exception as e:
            logger.error(f"Step-Back 改写失败: {e}")
            return query


# ===========================================================================
# 2. DataCleaner 数据清洗器
# ===========================================================================

class DataCleaner:
    """
    企业级文档数据清洗器
    提供两档清洗能力：
    - clean_text: 重量级清洗（用于入库前的全文清洗）
    - clean_for_embedding: 轻量级清洗（用于嵌入前的文本预处理）
    """

    # 广告/水印/噪音关键词
    _NOISE_KEYWORDS = [
        "版权所有", "Copyright", "All Rights Reserved",
        "未经许可不得转载", "关注公众号", "扫码关注",
        "加入社群", "点击链接", "广告", "赞助商",
        "免责声明", "本文不构成投资建议",
    ]

    # 判断是否为乱码行（特殊字符占比超过 50%）
    @staticmethod
    def _is_garbage_line(line: str) -> bool:
        """
        判断一行文本是否为乱码。
        当非中文字符、非英文字母、非常见标点、非数字的字符占比超过 50% 时，
        判定为乱码。

        :param line: 待判断的文本行
        :return: 是否为乱码
        """
        if not line:
            return True
        total = len(line)
        if total == 0:
            return True
        # 常见正常字符：中文、英文、数字、常见标点
        normal = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303fa-zA-Z0-9\s，。！？；：""''、（）\-\.\,\!\?\;\:\(\)\[\]\/]', line))
        return normal / total < 0.5

    @staticmethod
    def clean_text(text: str) -> str:
        """
        企业级文档清洗流水线，执行以下步骤：
        1. 移除页眉页脚（出现在超过 50% 页面的短行）
        2. 过滤空白段落（长度 < 5 的行）
        3. 过滤乱码行（特殊字符占比 > 50%）
        4. 广告/水印关键词过滤
        5. 去重（连续重复段落）

        :param text: 原始文档文本
        :return: 清洗后的文本
        """
        if not text:
            return ""

        lines = text.split("\n")
        total_lines = len(lines)
        if total_lines == 0:
            return ""

        # ---- 步骤 1：移除页眉页脚 ----
        # 统计每行出现次数，短行（<=20字符）出现超过50%页面的视为页眉/页脚
        line_counter = Counter(line.strip() for line in lines if line.strip())
        header_footer_lines = set()
        threshold = max(1, total_lines // 2)
        for line_text, count in line_counter.items():
            if len(line_text) <= 20 and count >= threshold:
                header_footer_lines.add(line_text)

        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # 跳过页眉页脚
            if stripped in header_footer_lines:
                continue
            # ---- 步骤 2：过滤空白段落 ----
            if len(stripped) < 5:
                continue
            # ---- 步骤 3：过滤乱码 ----
            if DataCleaner._is_garbage_line(stripped):
                continue
            # ---- 步骤 4：广告/水印关键词过滤 ----
            if any(kw in stripped for kw in DataCleaner._NOISE_KEYWORDS):
                continue
            cleaned_lines.append(stripped)

        # ---- 步骤 5：去重（连续重复段落） ----
        deduped_lines = []
        prev_line = None
        for line in cleaned_lines:
            if line == prev_line:
                continue
            deduped_lines.append(line)
            prev_line = line

        result = "\n".join(deduped_lines)
        logger.info(f"文档清洗完成: 原始 {total_lines} 行 -> 清洗后 {len(deduped_lines)} 行")
        return result

    @staticmethod
    def clean_for_embedding(text: str) -> str:
        """
        轻量级文本清洗，用于嵌入前的文本预处理。
        主要操作：去除多余空白、去除特殊控制字符、合并连续空行。

        :param text: 原始文本
        :return: 清洗后的文本
        """
        if not text:
            return ""
        # 去除控制字符（保留换行和制表符）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        # 合并连续空行为单个换行
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 去除行首行尾空白
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)
        # 去除首尾多余换行
        text = text.strip()
        return text


# ===========================================================================
# 3. SmartChunker 智能切片器
# ===========================================================================

class SmartChunker:
    """
    中文优化的智能文本切片器。
    使用 LangChain 的 RecursiveCharacterTextSplitter，配合中文标点分隔符，
    在保持语义完整性的前提下将长文档切分为适合嵌入的短文本块。
    每个 chunk 自动携带元数据（parent_doc、chunk_index、word_count、created_at）。
    """

    # 中文优化分隔符：优先在段落和句子边界切分
    _CHINESE_SEPARATORS = [
        "\n\n", "\n", "。", "！", "？", "；", "，", " ", ""
    ]

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: Optional[List[str]] = None,
    ):
        """
        初始化智能切片器。

        :param chunk_size: 每个 chunk 的最大字符数（默认 500）
        :param chunk_overlap: 相邻 chunk 之间的重叠字符数（默认 50）
        :param separators: 自定义分隔符列表（默认使用中文优化分隔符）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self._CHINESE_SEPARATORS
        self._splitter = RecursiveCharacterTextSplitter(
            separators=self.separators,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
        )

    def chunk_documents(
        self,
        texts: List[str],
        metadata_list: Optional[List[Dict]] = None,
    ) -> Tuple[List[str], List[Dict]]:
        """
        对一组文档文本进行智能切片，返回切片后的文本列表和对应的元数据列表。

        每个生成的 chunk 会携带以下元数据：
        - parent_doc: 父文档的原始文本（截取前 200 字作为标识）
        - chunk_index: 该 chunk 在父文档中的序号（从 0 开始）
        - word_count: chunk 的字符数
        - created_at: chunk 创建时间（ISO 格式）
        - 从 metadata_list 中继承的原始元数据

        :param texts: 文档文本列表
        :param metadata_list: 与 texts 对应的可选元数据列表
        :return: (chunk_texts, chunk_metadatas) 元组
        """
        all_chunks: List[str] = []
        all_metadatas: List[Dict] = []

        now = datetime.now(timezone.utc).isoformat()

        for doc_idx, text in enumerate(texts):
            if not text or not text.strip():
                continue

            parent_meta = metadata_list[doc_idx] if (metadata_list and doc_idx < len(metadata_list)) else {}

            chunks = self._splitter.split_text(text)

            for chunk_idx, chunk in enumerate(chunks):
                chunk_meta = {
                    "parent_doc": text[:200] if len(text) > 200 else text,
                    "chunk_index": chunk_idx,
                    "word_count": len(chunk),
                    "created_at": now,
                    **parent_meta,
                }
                all_chunks.append(chunk)
                all_metadatas.append(chunk_meta)

        logger.info(f"智能切片完成: {len(texts)} 篇文档 -> {len(all_chunks)} 个 chunk")
        return all_chunks, all_metadatas


# ===========================================================================
# 4. HybridRetriever 混合检索器
# ===========================================================================

class HybridRetriever:
    """
    混合检索器
    结合语义向量检索、BM25 关键词检索、RRF 融合排序和 MMR 多样性重排，
    提供高质量的多路召回能力。

    检索流程：
    1. （可选）Multi-Query 改写生成多个子查询
    2. （可选）HyDE 改写用假设文档辅助检索
    3. 对每个 query 变体执行语义检索（通过 chroma_client）
    4. 对原始 query 执行 BM25 关键词检索
    5. RRF（Reciprocal Rank Fusion）融合排序
    6. （可选）MMR（Maximal Marginal Relevance）多样性重排
    """

    def __init__(self):
        """初始化混合检索器，懒加载 Embedding 模型。"""
        self._embeddings: Optional[OpenAIEmbeddings] = None

    @property
    def embeddings(self) -> OpenAIEmbeddings:
        """懒加载获取 Embedding 实例，用于 MMR 重排时的相似度计算。"""
        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                model="text-embedding-v3",
                openai_api_key=settings.DASHSCOPE_API_KEY,
                openai_api_base=settings.LLM_BASE_URL,
            )
            logger.info("Embedding 模型初始化完成 (text-embedding-v3)")
        return self._embeddings

    # ---- 分词与 BM25 评分（复用项目已有逻辑） ----

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """
        简易中文分词：提取中文字符和英文单词。
        复用项目 agent_qa/tools.py 中的分词逻辑。

        :param text: 待分词文本
        :return: 分词结果列表
        """
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        english_words = re.findall(r'[a-zA-Z]+', text)
        return chinese_chars + english_words

    @staticmethod
    def _bm25_score(query_tokens: List[str], doc: str) -> float:
        """
        简易 BM25 关键词匹配评分。
        复用项目 agent_qa/tools.py 中的 BM25 评分逻辑。

        :param query_tokens: 查询分词结果
        :param doc: 文档文本
        :return: BM25 评分
        """
        doc_lower = doc.lower()
        score = 0.0
        for token in query_tokens:
            token_lower = token.lower()
            if token_lower in doc_lower:
                score += 1.0
                score += doc_lower.count(token_lower) * 0.3
        return score

    # ---- RRF 融合排序 ----

    @staticmethod
    def _rrf_fusion(
        semantic_results_list: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        k: int = 60,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Reciprocal Rank Fusion（RRF）融合排序。
        将多个语义检索结果列表和一组 BM25 结果通过倒数排名融合算法合并，
        消除单一检索策略的偏差，提升最终排序质量。

        公式：score(d) = sum( 1 / (k + rank) )  对所有包含文档 d 的排名列表

        :param semantic_results_list: 多个语义检索结果（chroma_client.search 返回格式）的列表
        :param bm25_results: BM25 关键词检索结果列表，每项含 id / doc / metadata / score
        :param k: RCF 平滑常数（默认 60）
        :return: 以 doc_id 为键的融合结果字典 {id: {"doc", "metadata", "score"}}
        """
        scores: Dict[str, Dict[str, Any]] = {}

        # 合并所有语义检索结果
        for semantic_results in semantic_results_list:
            if not semantic_results or not semantic_results.get("documents"):
                continue
            docs = semantic_results["documents"][0] if semantic_results["documents"] else []
            ids = semantic_results["ids"][0] if semantic_results.get("ids") else []
            metadatas = (
                semantic_results.get("metadatas", [[]])[0]
                if semantic_results.get("metadatas")
                else []
            )

            for rank, (doc_id, doc, meta) in enumerate(
                zip(ids, docs, metadatas)
            ):
                if doc_id not in scores:
                    scores[doc_id] = {"doc": doc, "metadata": meta, "score": 0.0}
                scores[doc_id]["score"] += 1.0 / (k + rank + 1)

        # 合并 BM25 结果
        for rank, item in enumerate(bm25_results):
            doc_id = item["id"]
            if doc_id not in scores:
                scores[doc_id] = {
                    "doc": item["doc"],
                    "metadata": item.get("metadata", {}),
                    "score": 0.0,
                }
            scores[doc_id]["score"] += 1.0 / (k + rank + 1)

        return scores

    # ---- MMR 多样性重排 ----

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """
        计算两个向量的余弦相似度。

        :param vec_a: 向量 A
        :param vec_b: 向量 B
        :return: 余弦相似度（-1.0 ~ 1.0）
        """
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _mmr_rerank_sync(
        self,
        candidates: List[Dict[str, Any]],
        query_embedding: List[float],
        k: int = 5,
        lambda_mult: float = 0.55,
    ) -> List[Dict[str, Any]]:
        """
        MMR 重排（同步版本）。
        """
        if not candidates:
            return []

        candidate_texts = [c["doc"] for c in candidates]
        try:
            doc_embeddings = self.embeddings.embed_documents(candidate_texts)
        except Exception as e:
            logger.error(f"MMR embedding 计算失败，退化为原始排序: {e}")
            return candidates[:k]

        relevance_scores = []
        for doc_emb in doc_embeddings:
            rel = self._cosine_similarity(query_embedding, doc_emb)
            relevance_scores.append(rel)

        selected_indices: List[int] = []
        remaining_indices = list(range(len(candidates)))

        for _ in range(min(k, len(candidates))):
            best_idx = None
            best_mmr = -float("inf")

            for idx in remaining_indices:
                relevance = relevance_scores[idx]

                if not selected_indices:
                    diversity_penalty = 0.0
                else:
                    max_sim = max(
                        self._cosine_similarity(
                            doc_embeddings[idx], doc_embeddings[sel_idx]
                        )
                        for sel_idx in selected_indices
                    )
                    diversity_penalty = max_sim

                mmr_score = lambda_mult * relevance - (1 - lambda_mult) * diversity_penalty

                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = idx

            if best_idx is not None:
                selected_indices.append(best_idx)
                remaining_indices.remove(best_idx)

        result = [candidates[i] for i in selected_indices]
        logger.info(f"MMR 重排完成: {len(candidates)} 个候选 -> {len(result)} 个结果")
        return result

    async def _mmr_rerank(
        self,
        candidates: List[Dict[str, Any]],
        query_embedding: List[float],
        k: int = 5,
        lambda_mult: float = 0.55,
    ) -> List[Dict[str, Any]]:
        """
        MMR（Maximal Marginal Relevance）贪心选择重排。
        在相关性和多样性之间取得平衡，避免返回高度冗余的结果。

        MMR 公式：score = lambda * relevance - (1 - lambda) * max_similarity_to_selected

        :param candidates: RRF 融合后的候选文档列表，每项含 id / doc / metadata / score
        :param query_embedding: 查询的向量表示
        :param k: 返回的文档数量
        :param lambda_mult: 相关性权重（0~1，越大越偏向相关性）
        :return: MMR 重排后的文档列表
        """
        if not candidates:
            return []

        # 为每个候选文档计算 embedding
        candidate_texts = [c["doc"] for c in candidates]
        try:
            doc_embeddings = await self.embeddings.aembed_documents(candidate_texts)
        except Exception as e:
            logger.error(f"MMR embedding 计算失败，退化为原始排序: {e}")
            return candidates[:k]

        # 预计算每个候选与 query 的相关性分数
        relevance_scores = []
        for doc_emb in doc_embeddings:
            rel = self._cosine_similarity(query_embedding, doc_emb)
            relevance_scores.append(rel)

        selected_indices: List[int] = []
        remaining_indices = list(range(len(candidates)))

        for _ in range(min(k, len(candidates))):
            best_idx = None
            best_mmr = -float("inf")

            for idx in remaining_indices:
                relevance = relevance_scores[idx]

                if not selected_indices:
                    diversity_penalty = 0.0
                else:
                    # 与已选文档的最大相似度
                    max_sim = max(
                        self._cosine_similarity(
                            doc_embeddings[idx], doc_embeddings[sel_idx]
                        )
                        for sel_idx in selected_indices
                    )
                    diversity_penalty = max_sim

                mmr_score = lambda_mult * relevance - (1 - lambda_mult) * diversity_penalty

                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = idx

            if best_idx is not None:
                selected_indices.append(best_idx)
                remaining_indices.remove(best_idx)

        result = [candidates[i] for i in selected_indices]
        logger.info(f"MMR 重排完成: {len(candidates)} 个候选 -> {len(result)} 个结果")
        return result

    # ---- 核心检索方法 ----

    async def retrieve(
        self,
        query: str,
        collection_name: str,
        n_results: int = 5,
        use_multi_query: bool = False,
        use_hyde: bool = False,
        use_mmr: bool = True,
    ) -> Dict[str, Any]:
        """
        核心混合检索方法。
        整合 Multi-Query / HyDE 改写、语义检索、BM25 检索、RRF 融合和 MMR 重排，
        返回高质量检索结果。

        :param query: 用户原始查询
        :param collection_name: ChromaDB 集合名称
        :param n_results: 返回结果数量（默认 5）
        :param use_multi_query: 是否启用 Multi-Query 改写（默认 False）
        :param use_hyde: 是否启用 HyDE 改写（默认 False）
        :param use_mmr: 是否启用 MMR 多样性重排（默认 True）
        :return: 检索结果字典，格式：
            {
                "results": [{"id", "doc", "metadata", "score"}],
                "queries_used": [...],
                "retrieval_type": "..."
            }
        """
        queries_used: List[str] = []
        semantic_results_list: List[Dict[str, Any]] = []

        # 构建查询变体列表
        query_variants = [query]
        queries_used.append(query)

        # ---- 步骤 1：Multi-Query 改写 ----
        if use_multi_query:
            try:
                multi_queries = await QueryRewriter.multi_query_rewrite(query)
                query_variants.extend(multi_queries[1:])  # 跳过原始 query（已在列表中）
                queries_used.extend(multi_queries[1:])
            except Exception as e:
                logger.warning(f"Multi-Query 改写失败，使用原始查询: {e}")

        # ---- 步骤 2：HyDE 改写 ----
        if use_hyde:
            try:
                hyde_doc = await QueryRewriter.hyde_rewrite(query)
                query_variants.append(hyde_doc)
                queries_used.append(f"[HyDE] {hyde_doc[:50]}...")
            except Exception as e:
                logger.warning(f"HyDE 改写失败，跳过: {e}")

        # ---- 步骤 3：对每个 query 变体执行语义检索 ----
        for qv in query_variants:
            try:
                results = chroma_client.search(
                    collection_name=collection_name,
                    query_text=qv,
                    n_results=n_results * 2,
                )
                semantic_results_list.append(results)
            except Exception as e:
                logger.warning(f"语义检索失败 (query: {qv[:50]}...): {e}")

        # ---- 步骤 4：对原始 query 执行 BM25 关键词检索 ----
        bm25_results: List[Dict[str, Any]] = []
        try:
            collection = chroma_client.get_or_create_collection(collection_name)
            all_docs = collection.get()

            if all_docs and all_docs.get("documents"):
                query_tokens = self._tokenize(query)
                for i, doc in enumerate(all_docs["documents"]):
                    if doc:
                        meta = (
                            all_docs["metadatas"][i]
                            if all_docs.get("metadatas") and i < len(all_docs["metadatas"])
                            else {}
                        )
                        doc_id = (
                            all_docs["ids"][i]
                            if i < len(all_docs["ids"])
                            else str(i)
                        )
                        score = self._bm25_score(query_tokens, doc)
                        bm25_results.append({
                            "id": doc_id,
                            "doc": doc,
                            "metadata": meta,
                            "score": score,
                        })

                bm25_results.sort(key=lambda x: x["score"], reverse=True)
                bm25_results = bm25_results[: n_results * 2]
        except Exception as e:
            logger.warning(f"BM25 检索失败: {e}")

        # ---- 步骤 5：RRF 融合排序 ----
        fused_scores = self._rrf_fusion(semantic_results_list, bm25_results, k=60)
        sorted_results = sorted(
            fused_scores.values(), key=lambda x: x["score"], reverse=True
        )
        # 转换为标准输出格式
        candidates = [
            {
                "id": doc_id,
                "doc": item["doc"],
                "metadata": item.get("metadata", {}),
                "score": item["score"],
            }
            for doc_id, item in fused_scores.items()
        ]
        candidates.sort(key=lambda x: x["score"], reverse=True)

        # ---- 步骤 6：MMR 多样性重排 ----
        retrieval_type = "semantic+bm25_rrf"
        final_results = candidates[: n_results * 2]

        if use_mmr and candidates:
            try:
                query_embedding = await self.embeddings.aembed_query(query)
                final_results = await self._mmr_rerank(
                    candidates=candidates[: n_results * 2],
                    query_embedding=query_embedding,
                    k=n_results,
                    lambda_mult=0.55,
                )
                retrieval_type = "semantic+bm25_rrf+mmr"
            except Exception as e:
                logger.warning(f"MMR 重排失败，使用 RRF 排序结果: {e}")
                final_results = candidates[:n_results]

        # 确保返回 n_results 条
        final_results = final_results[:n_results]

        # 补充 id 字段（fused_scores 字典的 key 就是 id）
        for item in final_results:
            if "id" not in item:
                # 从 fused_scores 反查 id
                for doc_id, v in fused_scores.items():
                    if v["doc"] == item["doc"]:
                        item["id"] = doc_id
                        break

        logger.info(
            f"混合检索完成: collection='{collection_name}', "
            f"查询数={len(queries_used)}, 结果数={len(final_results)}, "
            f"类型={retrieval_type}"
        )

        return {
            "results": final_results,
            "queries_used": queries_used,
            "retrieval_type": retrieval_type,
        }

    def retrieve_sync(
        self,
        query: str,
        collection_name: str,
        n_results: int = 5,
        use_multi_query: bool = False,
        use_hyde: bool = False,
        use_mmr: bool = True,
    ) -> Dict[str, Any]:
        """
        核心混合检索方法（同步版本）。
        用于同步调用场景（如 LangChain ReAct Agent 的同步工具函数），
        避免 uvicorn 事件循环冲突。

        :param query: 用户原始查询
        :param collection_name: ChromaDB 集合名称
        :param n_results: 返回结果数量（默认 5）
        :param use_multi_query: 是否启用 Multi-Query 改写（默认 False）
        :param use_hyde: 是否启用 HyDE 改写（默认 False）
        :param use_mmr: 是否启用 MMR 多样性重排（默认 True）
        :return: 检索结果字典
        """
        queries_used: List[str] = []
        semantic_results_list: List[Dict[str, Any]] = []

        query_variants = [query]
        queries_used.append(query)

        # ---- 步骤 1：Multi-Query 改写（同步） ----
        if use_multi_query:
            try:
                multi_queries = QueryRewriter.multi_query_rewrite_sync(query)
                query_variants.extend(multi_queries[1:])
                queries_used.extend(multi_queries[1:])
            except Exception as e:
                logger.warning(f"Multi-Query 改写失败，使用原始查询: {e}")

        # ---- 步骤 2：HyDE 改写（同步） ----
        if use_hyde:
            try:
                prompt = ChatPromptTemplate.from_messages([
                    ("human", QueryRewriter._HYDE_TEMPLATE),
                ])
                chain = prompt | llm_service.llm | StrOutputParser()
                hyde_doc = chain.invoke({"question": query})
                query_variants.append(hyde_doc.strip())
                queries_used.append(f"[HyDE] {hyde_doc[:50]}...")
            except Exception as e:
                logger.warning(f"HyDE 改写失败，跳过: {e}")

        # ---- 步骤 3：语义检索 ----
        for qv in query_variants:
            try:
                results = chroma_client.search(
                    collection_name=collection_name,
                    query_text=qv,
                    n_results=n_results * 2,
                )
                semantic_results_list.append(results)
            except Exception as e:
                logger.warning(f"语义检索失败 (query: {qv[:50]}...): {e}")

        # ---- 步骤 4：BM25 关键词检索 ----
        bm25_results: List[Dict[str, Any]] = []
        try:
            collection = chroma_client.get_or_create_collection(collection_name)
            all_docs = collection.get()

            if all_docs and all_docs.get("documents"):
                query_tokens = self._tokenize(query)
                for i, doc in enumerate(all_docs["documents"]):
                    if doc:
                        meta = (
                            all_docs["metadatas"][i]
                            if all_docs.get("metadatas") and i < len(all_docs["metadatas"])
                            else {}
                        )
                        doc_id = (
                            all_docs["ids"][i]
                            if i < len(all_docs["ids"])
                            else str(i)
                        )
                        score = self._bm25_score(query_tokens, doc)
                        bm25_results.append({
                            "id": doc_id,
                            "doc": doc,
                            "metadata": meta,
                            "score": score,
                        })

                bm25_results.sort(key=lambda x: x["score"], reverse=True)
                bm25_results = bm25_results[:n_results * 2]
        except Exception as e:
            logger.warning(f"BM25 检索失败: {e}")

        # ---- 步骤 5：RRF 融合排序 ----
        fused_scores = self._rrf_fusion(semantic_results_list, bm25_results, k=60)
        candidates = [
            {
                "id": doc_id,
                "doc": item["doc"],
                "metadata": item.get("metadata", {}),
                "score": item["score"],
            }
            for doc_id, item in fused_scores.items()
        ]
        candidates.sort(key=lambda x: x["score"], reverse=True)

        # ---- 步骤 6：MMR 多样性重排（同步） ----
        retrieval_type = "semantic+bm25_rrf"
        final_results = candidates[:n_results * 2]

        if use_mmr and candidates:
            try:
                query_embedding = self.embeddings.embed_query(query)
                final_results = self._mmr_rerank_sync(
                    candidates=candidates[:n_results * 2],
                    query_embedding=query_embedding,
                    k=n_results,
                    lambda_mult=0.55,
                )
                retrieval_type = "semantic+bm25_rrf+mmr"
            except Exception as e:
                logger.warning(f"MMR 重排失败，使用 RRF 排序结果: {e}")
                final_results = candidates[:n_results]

        final_results = final_results[:n_results]

        for item in final_results:
            if "id" not in item:
                for doc_id, v in fused_scores.items():
                    if v["doc"] == item["doc"]:
                        item["id"] = doc_id
                        break

        logger.info(
            f"混合检索完成: collection='{collection_name}', "
            f"查询数={len(queries_used)}, 结果数={len(final_results)}, "
            f"类型={retrieval_type}"
        )

        return {
            "results": final_results,
            "queries_used": queries_used,
            "retrieval_type": retrieval_type,
        }


# ===========================================================================
# 5. 文档去重合并
# ===========================================================================

def merge_and_deduplicate_results(multi_query_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    对多个查询返回的检索结果按文档 id 去重合并。
    当多个查询返回相同的文档时，只保留得分最高的那份，避免冗余。

    :param multi_query_results: 多个查询的检索结果列表，每个元素为 retrieve() 返回的字典
    :return: 去重合并后的结果字典，格式：
        {
            "results": [{"id", "doc", "metadata", "score"}],
            "queries_used": [...],
            "retrieval_type": "merged_deduplicated"
        }
    """
    merged: Dict[str, Dict[str, Any]] = {}
    all_queries_used: List[str] = []

    for result_dict in multi_query_results:
        # 收集所有使用过的查询
        for q in result_dict.get("queries_used", []):
            if q not in all_queries_used:
                all_queries_used.append(q)

        for item in result_dict.get("results", []):
            doc_id = item.get("id")
            if not doc_id:
                continue

            if doc_id not in merged:
                merged[doc_id] = {
                    "id": doc_id,
                    "doc": item.get("doc", ""),
                    "metadata": item.get("metadata", {}),
                    "score": item.get("score", 0.0),
                }
            else:
                # 保留更高分数
                if item.get("score", 0.0) > merged[doc_id]["score"]:
                    merged[doc_id]["score"] = item.get("score", 0.0)

    # 按分数降序排列
    sorted_results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)

    logger.info(
        f"文档去重合并完成: {len(multi_query_results)} 个查询结果 -> "
        f"{len(sorted_results)} 个去重文档"
    )

    return {
        "results": sorted_results,
        "queries_used": all_queries_used,
        "retrieval_type": "merged_deduplicated",
    }
