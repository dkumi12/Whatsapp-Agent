import os
import sys
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.vector_store import get_all_chat_messages, get_all_lesson_video_urls, add_lesson_to_kb
from src.youtube_ingestion import fetch_and_structure_transcript

def scan_and_ingest():
    print("🔍 Scanning Postgres Chat Archive for YouTube links...")

    # 1. Fetch all chat messages
    chat_messages = get_all_chat_messages()

    # 2. Extract URLs using Regex
    # Matches standard youtube.com and youtu.be links
    youtube_regex = r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+)'

    found_links = {} # url -> cohort_tag
    for row in chat_messages:
        doc = row.get("content")
        if not doc:
            continue
        matches = re.findall(youtube_regex, doc)
        for match in matches:
            cohort_tag = row.get("cohort_tag") or "Cohort Group"
            found_links[match] = cohort_tag

    print(f"✅ Found {len(found_links)} unique YouTube links in chat history.")

    # 3. Filter out already ingested
    ingested_urls = get_all_lesson_video_urls()
    
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
