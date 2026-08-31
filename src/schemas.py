from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class MessageClassification(BaseModel):
    category: Literal["ANNOUNCEMENT", "ASSIGNMENT_DEADLINE", "STUDENT_QUESTION", "CHITCHAT", "RESOURCE_SHARE"] = Field(
        description="Categorization of incoming cohort chat message"
    )
    is_urgent: bool = Field(description="True if prefect or students need immediate awareness")
    summary: str = Field(description="One-sentence summary of the message")
    extracted_deadline: Optional[str] = Field(None, description="Due date or time if mentioned")
    topics: List[str] = Field(default_factory=list, description="Key topics, tools, or concepts mentioned")

class LessonTopicChunk(BaseModel):
    start_seconds: int = Field(description="Timestamp in seconds when this topic starts")
    timestamp_str: str = Field(description="Formatted timestamp e.g. '14:20'")
    topic: str = Field(description="Core concept or question addressed")
    summary: str = Field(description="Explanatory notes, definitions, and code syntax")
    key_takeaways: List[str] = Field(default_factory=list, description="Important rules or instructor tips")

class LessonKnowledgeDoc(BaseModel):
    video_id: str
    video_title: str
    video_url: str
    chunks: List[LessonTopicChunk]

class WhatsAppWebhookPayload(BaseModel):
    group_id: str
    sender: str
    message: str
    timestamp: Optional[int] = None
    is_private: Optional[bool] = False
