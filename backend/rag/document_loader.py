from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from backend.config.settings import settings
import os

class DocumentProcessor:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=settings.DASHSCOPE_API_KEY,
            openai_api_base=settings.LLM_BASE_URL
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len
        )
    
    def load_document(self, file_path: str) -> list[Document]:
        if file_path.endswith('.pdf'):
            loader = PyPDFLoader(file_path)
        else:
            loader = TextLoader(file_path)
        return loader.load()
    
    def split_documents(self, documents: list[Document]) -> list[Document]:
        return self.text_splitter.split_documents(documents)
    
    def create_vectorstore(self, documents: list[Document], collection_name: str):
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name=collection_name,
            persist_directory="./chroma_db"
        )
        return vectorstore

document_processor = DocumentProcessor()