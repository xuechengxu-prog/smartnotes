from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from backend.rag import document_processor, RAGRetriever
from langchain_core.documents import Document
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="知识库管理 API", version="1.0")

class TextDocument(BaseModel):
    content: str
    collection_name: str = "default"
    metadata: dict = {}

@app.post("/knowledge/add/text")
async def add_text_document(doc: TextDocument):
    try:
        document = Document(
            page_content=doc.content,
            metadata=doc.metadata
        )
        
        processor = document_processor
        vectorstore = processor.create_vectorstore(
            [document], 
            doc.collection_name
        )
        
        logger.info(f"文档已添加到知识库，collection: {doc.collection_name}")
        return {"status": "success", "message": "文档已添加"}
    except Exception as e:
        logger.error(f"添加文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/knowledge/add/file")
async def add_file_document(
    file: UploadFile = File(...),
    collection_name: str = "default"
):
    try:
        contents = await file.read()
        text = contents.decode('utf-8')
        
        document = Document(page_content=text, metadata={"source": file.filename})
        
        processor = document_processor
        vectorstore = processor.create_vectorstore(
            [document], 
            collection_name
        )
        
        logger.info(f"文件已添加到知识库: {file.filename}")
        return {"status": "success", "message": f"文件 {file.filename} 已添加"}
    except Exception as e:
        logger.error(f"添加文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge/search")
async def search_knowledge(
    query: str,
    collection_name: str = "default",
    k: int = 3
):
    try:
        retriever = RAGRetriever(collection_name)
        retriever.load_vectorstore()
        docs = retriever.retrieve(query, k=k)
        
        results = [
            {
                "content": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in docs
        ]
        
        return {"results": results}
    except Exception as e:
        logger.error(f"搜索失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)