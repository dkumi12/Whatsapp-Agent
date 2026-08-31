import re
import uuid
from typing import Optional, List, Dict, Any
import chromadb
from src.config import settings
from src.schemas import LessonKnowledgeDoc

chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)

# 1. Video Lessons & Docs Collection
lesson_collection = chroma_client.get_or_create_collection(name="cohort_knowledge_base")

# 2. Historical Group Chat Messages Collection
chat_collection = chroma_client.get_or_create_collection(name="cohort_chat_archive")

def add_lesson_to_kb(lesson: LessonKnowledgeDoc, cohort_tag: str = "Cohort 1"):
    documents = []
    metadatas = []
    ids = []
    
    for idx, chunk in enumerate(lesson.chunks):
        doc_id = f"{lesson.video_id}_chunk_{idx}"
        deep_link = f"{lesson.video_url}&t={chunk.start_seconds}s"
        content = f"[{cohort_tag}] Topic: {chunk.topic}\nTimestamp: {chunk.timestamp_str}\nSummary: {chunk.summary}\nTakeaways: {', '.join(chunk.key_takeaways)}"
        
        documents.append(content)
        ids.append(doc_id)
        metadatas.append({
            "video_id": lesson.video_id,
            "video_title": lesson.video_title,
            "timestamp": chunk.timestamp_str,
            "deep_link": deep_link,
            "topic": chunk.topic,
            "cohort_tag": cohort_tag
        })
    
    if documents:
        lesson_collection.upsert(documents=documents, ids=ids, metadatas=metadatas)

def get_all_ingested_lessons() -> List[Dict[str, Any]]:
    """Returns all parsed video lessons grouped by video ID from ChromaDB"""
    results = lesson_collection.get()
    if not results or not results['documents']:
        return []
    
    lessons = {}
    for doc, meta in zip(results['documents'], results['metadatas']):
        v_id = meta.get('video_id', 'unknown')
        if v_id not in lessons:
            lessons[v_id] = {
                "video_id": v_id,
                "video_title": meta.get('video_title', 'Video Lesson'),
                "cohort_tag": meta.get('cohort_tag', 'Cohort 1'),
                "chunks": []
            }
        lessons[v_id]["chunks"].append({
            "topic": meta.get('topic', 'Topic'),
            "timestamp": meta.get('timestamp', '00:00'),
            "deep_link": meta.get('deep_link', ''),
            "content": doc
        })
    return list(lessons.values())

def query_kb(query_text: str, cohort_tag: Optional[str] = None, n_results: int = 4) -> str:
    where_filter = {"cohort_tag": cohort_tag} if cohort_tag else None
    results = lesson_collection.query(query_texts=[query_text], n_results=n_results, where=where_filter)
    if not results or not results['documents'] or not results['documents'][0]:
        return "No specific lesson context found."
    
    context_chunks = []
    for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
        context_chunks.append(f"[{meta.get('cohort_tag', 'Cohort')} | {meta.get('topic', 'Lesson')} at {meta.get('timestamp', '')}] (Link: {meta.get('deep_link', '')}):\n{doc}")
    
    return "\n\n".join(context_chunks)

def add_chat_message_to_archive(sender: str, message: str, group_id: str, cohort_tag: str = "Cohort 1", category: str = "GENERAL", summary: str = "", deadline: str = ""):
    doc_id = str(uuid.uuid4())
    content = f"[{cohort_tag}] From {sender} ({category}): {message}"
    if summary:
        content += f"\nSummary: {summary}"
    if deadline:
        content += f"\nDeadline: {deadline}"
        
    chat_collection.upsert(
        documents=[content],
        ids=[doc_id],
        metadatas=[{
            "sender": sender,
            "group_id": group_id,
            "cohort_tag": cohort_tag,
            "category": category,
            "deadline": deadline or "",
            "summary": summary or ""
        }]
    )

def query_chat_archive(query_text: str, cohort_tag: Optional[str] = None, n_results: int = 8) -> str:
    where_filter = {"cohort_tag": cohort_tag} if cohort_tag else None
    results = chat_collection.query(query_texts=[query_text], n_results=n_results, where=where_filter)
    if not results or not results['documents'] or not results['documents'][0]:
        return "No past chat messages found matching this query."
    
    chat_results = []
    for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
        chat_results.append(f"• [{meta.get('cohort_tag', 'Cohort')}] {doc}")
    return "\n\n".join(chat_results)

def get_recent_catchup_context(cohort_tag: Optional[str] = None, n_results: int = 25) -> str:
    if chat_collection.count() == 0:
        return "No chat history has been ingested yet. Please upload your WhatsApp chat export on the dashboard."
    
    search_queries = ["announcement deadline assignment project homework submission schedule link recording test"]
    where_filter = {"cohort_tag": cohort_tag} if cohort_tag else None
    
    results = chat_collection.query(
        query_texts=search_queries, 
        n_results=min(n_results, chat_collection.count()),
        where=where_filter
    )
    
    matched_docs = []
    if results and results['documents'] and results['documents'][0]:
        matched_docs.extend(results['documents'][0])
        
    recent = chat_collection.get(limit=15)
    if recent and recent['documents']:
        for d in recent['documents']:
            if d not in matched_docs:
                matched_docs.append(d)
                
    return "\n\n".join(matched_docs[:n_results])

def ingest_whatsapp_chat_export_text(raw_text: str, cohort_tag: str = "Cohort 1", group_id: str = "cohort_history") -> int:
    pattern = r'(?:\[?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\]?)\s*(?:- )?([^:]+):\s*(.+)'
    
    documents = []
    ids = []
    metadatas = []
    count = 0
    
    for match in re.finditer(pattern, raw_text):
        date, time, sender, message = match.groups()
        message_clean = message.strip()
        sender_clean = sender.strip()
        
        if "<Media omitted>" in message_clean or "Messages and calls are end-to-end encrypted" in message_clean:
            continue
        
        doc_id = str(uuid.uuid4())
        content = f"[{cohort_tag}] Date: {date} {time} | Sender: {sender_clean}\nMessage: {message_clean}"
        documents.append(content)
        ids.append(doc_id)
        metadatas.append({
            "sender": sender_clean,
            "group_id": group_id,
            "cohort_tag": cohort_tag,
            "date": date,
            "category": "HISTORICAL_CHAT"
        })
        count += 1
        
        if len(documents) >= 50:
            chat_collection.upsert(documents=documents, ids=ids, metadatas=metadatas)
            documents, ids, metadatas = [], [], []
            
    if documents:
        chat_collection.upsert(documents=documents, ids=ids, metadatas=metadatas)
        
    return count
