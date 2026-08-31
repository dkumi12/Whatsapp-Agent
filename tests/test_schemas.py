from src.schemas import MessageClassification, LessonTopicChunk, LessonKnowledgeDoc

def test_message_classification_schema():
    data = MessageClassification(
        category="ASSIGNMENT_DEADLINE",
        is_urgent=True,
        summary="Homework 2 is due on Friday at 5 PM",
        extracted_deadline="Friday 5 PM",
        topics=["Homework 2", "FastAPI"]
    )
    assert data.category == "ASSIGNMENT_DEADLINE"
    assert data.is_urgent is True
    assert "FastAPI" in data.topics

def test_lesson_knowledge_doc_schema():
    chunk = LessonTopicChunk(
        start_seconds=120,
        timestamp_str="02:00",
        topic="LangGraph State Setup",
        summary="Explanation of TypedDict state keys",
        key_takeaways=["State is immutable between nodes"]
    )
    doc = LessonKnowledgeDoc(
        video_id="abc12345678",
        video_title="LangGraph Deep Dive",
        video_url="https://youtube.com/watch?v=abc12345678",
        chunks=[chunk]
    )
    assert len(doc.chunks) == 1
    assert doc.chunks[0].start_seconds == 120
