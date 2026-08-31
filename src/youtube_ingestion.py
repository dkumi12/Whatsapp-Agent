import re
from youtube_transcript_api import YouTubeTranscriptApi
from src.schemas import LessonKnowledgeDoc
from src.config import get_llm

def extract_video_id(url: str) -> str:
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:&|\?|$)",
        r"youtu\.be\/([0-9A-Za-z_-]{11})"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract a valid YouTube video ID from {url}")

def fetch_and_structure_transcript(url: str, title: str = "Bootcamp Lesson") -> LessonKnowledgeDoc:
    video_id = extract_video_id(url)
    
    # 1. Fetch transcript with compatibility for both old & new youtube_transcript_api
    ytt = YouTubeTranscriptApi()
    if hasattr(ytt, "fetch"):
        transcript_list = ytt.fetch(video_id)
    elif hasattr(YouTubeTranscriptApi, "get_transcript"):
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US'])
    else:
        raise RuntimeError("No compatible transcript fetch method found on YouTubeTranscriptApi")
    
    formatted_lines = []
    for item in transcript_list:
        text = getattr(item, 'text', None) if not isinstance(item, dict) else item.get('text', '')
        start = getattr(item, 'start', 0) if not isinstance(item, dict) else item.get('start', 0)
        
        mins = int(start // 60)
        secs = int(start % 60)
        time_str = f"[{mins:02d}:{secs:02d}]"
        formatted_lines.append(f"{time_str} {text}")
    
    full_transcript = "\n".join(formatted_lines)
    
    # 2. LLM structuring into topic chunks
    llm = get_llm().with_structured_output(LessonKnowledgeDoc)
    prompt = f"""
    You are an AI teaching assistant for a technical bootcamp.
    Extract structured topic chunks with start timestamps and core explanations from this lesson transcript.
    
    Title: {title}
    Video ID: {video_id}
    Video URL: {url}
    
    Transcript Sample:
    {full_transcript[:12000]}
    """
    structured_doc = llm.invoke(prompt)
    return structured_doc
