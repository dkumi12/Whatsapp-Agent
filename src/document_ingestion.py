import os
import base64
import tempfile
import uuid
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from src.vector_store import add_raw_chunks_to_kb

def ingest_base64_pdf(base64_data: str, file_name: str, cohort_tag: str) -> int:
    """
    Decodes a base64 PDF, extracts text using PyPDFLoader, chunks it,
    and upserts into the lesson_chunks table.
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
        
        raw_chunks = []
        for chunk in chunks:
            # We prefix the chunk text with the document name for context
            page_num = chunk.metadata.get('page', 0) + 1
            content = f"[Document: {file_name} | Page {page_num}]\n{chunk.page_content}"

            raw_chunks.append({
                "id": str(uuid.uuid4()),
                "video_id": f"doc_{uuid.uuid4().hex[:8]}",  # re-using the lesson schema format
                "video_title": file_name,
                "video_url": "whatsapp_document_upload",
                "timestamp": None,
                "deep_link": None,
                "cohort_tag": cohort_tag,
                "topic": f"Document: {file_name}",
                "content": content
            })

        add_raw_chunks_to_kb(raw_chunks)
        return len(raw_chunks)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
