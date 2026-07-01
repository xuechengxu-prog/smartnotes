from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from backend.config.settings import settings

class RAGRetriever:
    def __init__(self, collection_name: str = "default"):
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=settings.DASHSCOPE_API_KEY,
            openai_api_base=settings.LLM_BASE_URL
        )
        self.collection_name = collection_name
        self.vectorstore = None
    
    def load_vectorstore(self):
        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory="./chroma_db"
        )
        return self.vectorstore
    
    def retrieve(self, query: str, k: int = 3) -> list[Document]:
        if not self.vectorstore:
            self.load_vectorstore()
        return self.vectorstore.similarity_search(query, k=k)
    
    def get_relevant_context(self, query: str, k: int = 3) -> str:
        docs = self.retrieve(query, k=k)
        context = "\n\n".join([doc.page_content for doc in docs])
        return context

class RAGChain:
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