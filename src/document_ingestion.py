import os
import base64
import tempfile
import uuid
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from src.vector_store import lesson_collection

def ingest_base64_pdf(base64_data: str, file_name: str, cohort_tag: str) -> int:
    """
    Decodes a base64 PDF, extracts text using PyPDFLoader, chunks it,
    and upserts into the ChromaDB lesson_collection.
    Returns the number of chunks ingested.
    """
    pdf_bytes = base64.b64decode(base64_data)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
        
    try:
        loader = PyPDFLoader(tmp_path)
        pages = loader.load()
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        chunks = text_splitter.split_documents(pages)
        
        docs = []
        metas = []
        ids = []
        for i, chunk in enumerate(chunks):
            # We prefix the chunk text with the document name for context
            page_num = chunk.metadata.get('page', 0) + 1
            docs.append(f"[Document: {file_name} | Page {page_num}]\n{chunk.page_content}")
            
            metas.append({
                "video_id": f"doc_{uuid.uuid4().hex[:8]}", # re-using the video metadata schema format
                "video_title": file_name,
                "video_url": "whatsapp_document_upload",
                "cohort_tag": cohort_tag,
                "topic": f"Document: {file_name}"
            })
            ids.append(str(uuid.uuid4()))
            
        if docs:
            lesson_collection.upsert(documents=docs, metadatas=metas, ids=ids)
            
        return len(docs)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
