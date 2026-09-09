import os
import sys
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.vector_store import chat_collection, lesson_collection, add_lesson_to_kb
from src.youtube_ingestion import fetch_and_structure_transcript

def get_already_ingested_urls():
    """Fetch all URLs that are already in the knowledge base."""
    results = lesson_collection.get(include=["metadatas"])
    ingested_urls = set()
    for meta in results.get("metadatas", []):
        if meta and "video_url" in meta:
            ingested_urls.add(meta["video_url"])
    return ingested_urls

def scan_and_ingest():
    print("🔍 Scanning ChromaDB Chat Archive for YouTube links...")
    
    # 1. Fetch all chat messages
    chat_results = chat_collection.get(include=["documents", "metadatas"])
    documents = chat_results.get("documents", [])
    metadatas = chat_results.get("metadatas", [])
    
    # 2. Extract URLs using Regex
    # Matches standard youtube.com and youtu.be links
    youtube_regex = r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+)'
    
    found_links = {} # url -> cohort_tag
    for doc, meta in zip(documents, metadatas):
        if not doc:
            continue
        matches = re.findall(youtube_regex, doc)
        for match in matches:
            cohort_tag = meta.get("cohort_tag", "Cohort Group") if meta else "Cohort Group"
            found_links[match] = cohort_tag
            
    print(f"✅ Found {len(found_links)} unique YouTube links in chat history.")
    
    # 3. Filter out already ingested
    ingested_urls = get_already_ingested_urls()
    
    # Normalize URLs for comparison (sometimes they have trailing slashes or differing formats, but regex catches base)
    new_links = {url: cohort for url, cohort in found_links.items() if url not in ingested_urls}
    print(f"🎯 {len(new_links)} of these are NEW and need to be ingested.\n")
    
    # 4. Ingest new links
    success_count = 0
    for idx, (url, cohort) in enumerate(new_links.items(), 1):
        print(f"[{idx}/{len(new_links)}] Ingesting {url} for {cohort}...")
        try:
            doc = fetch_and_structure_transcript(url, title=f"Retroactive Scan ({cohort})")
            add_lesson_to_kb(doc, cohort_tag=cohort)
            print(f"   -> Success! Added {len(doc.chunks)} chunks.\n")
            success_count += 1
        except Exception as e:
            print(f"   -> Failed: {e}\n")
            
    print(f"🎉 Retroactive scan complete. Successfully ingested {success_count} new videos.")

if __name__ == "__main__":
    scan_and_ingest()
