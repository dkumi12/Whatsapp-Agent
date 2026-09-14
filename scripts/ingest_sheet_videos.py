import os
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.youtube_ingestion import fetch_and_structure_transcript
from src.vector_store import add_lesson_to_kb, lesson_count

lessons = [
    ('Open Day', 'https://youtu.be/aNUE0awAjfk', 'Cohort 1'),
    ('Cloud and AI Cohort Project Review', 'https://youtu.be/Ds_9d45PguA', 'Cohort 1'),
    ('Linux Intro - Session 1', 'https://youtu.be/2vxqyFIqCPE', 'Cohort 1'),
    ('Linux Intro - Session 2', 'https://youtu.be/1Utk4aNItfM', 'Cohort 1'),
    ('Linux Intro - Session 3', 'https://youtu.be/a2kI4vF1Dwc', 'Cohort 1'),
    ('Lesson 1', 'https://youtu.be/DC2ucfoiHy0', 'Cohort 1'),
    ('Lesson 2', 'https://youtu.be/u2jz3gTFWU0', 'Cohort 1'),
    ('Extra Recording', 'https://youtu.be/wfZYxNMvY_8', 'Cohort 1'),
    ('Lesson 3 - Intro to GitHub', 'https://youtu.be/A89M7-oUDYE', 'Cohort 1'),
    ('Python 1', 'https://youtu.be/MXYXBm2R6Pw', 'Cohort 2'),
    ('Python 2', 'https://youtu.be/OBGYlxm8UzQ', 'Cohort 2'),
    ('Python 3 - Loops', 'https://youtu.be/hYDsrW0CuSg', 'Cohort 2'),
    ('Python 4 - Functions', 'https://youtu.be/r1cZ16cqq0g', 'Cohort 2'),
    ('Python 5 - APIs 1', 'https://youtu.be/cMaBtfRLOhU', 'Cohort 2'),
    ('Python 6 - APIs 2', 'https://youtu.be/fy9F31OaPOQ', 'Cohort 2'),
    ('Python 7 - APIs 3', 'https://youtu.be/gHLxIRrBJSg', 'Cohort 2'),
    ('Python 8 - APIs 4', 'https://youtu.be/bOBb77nvq0k', 'Cohort 2'),
    ('Python for DE - VS Code', 'https://youtu.be/7u4v5NhihAE', 'Cohort 2'),
]

print(f"Starting batch ingestion of {len(lessons)} curriculum videos into ChromaDB...\n")
success_count = 0

for idx, (title, url, cohort) in enumerate(lessons, 1):
    print(f"[{idx}/{len(lessons)}] Processing: '{title}' ({cohort}) - {url}")
    try:
        doc = fetch_and_structure_transcript(url, title)
        add_lesson_to_kb(doc, cohort_tag=cohort)
        print(f"   -> Successfully added {len(doc.chunks)} topic chunks!\n")
        success_count += 1
        time.sleep(1)
    except Exception as e:
        print(f"   -> Notice on '{title}': {e}\n")

print(f"Batch ingestion complete! Successfully indexed {success_count}/{len(lessons)} lectures.")
print(f"Total Knowledge Base Chunks in Postgres: {lesson_count()}")
