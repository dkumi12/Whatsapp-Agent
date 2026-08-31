import io
import os
import zipfile
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from src.schemas import WhatsAppWebhookPayload, LessonKnowledgeDoc
from src.graph import copilot_graph
from src.youtube_ingestion import fetch_and_structure_transcript
from src.vector_store import (
    add_lesson_to_kb, 
    query_kb, 
    lesson_collection, 
    chat_collection, 
    ingest_whatsapp_chat_export_text,
    query_chat_archive,
    get_recent_catchup_context,
    get_all_ingested_lessons
)
from src.config import settings, get_llm

app = FastAPI(title="Cohort Copilot Backend", version="1.0.0")

message_history: List[Dict[str, Any]] = []

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Cohort Copilot API"}

@app.get("/api/stats")
def get_stats():
    kb_count = lesson_collection.count() if lesson_collection else 0
    chat_count = chat_collection.count() if chat_collection else 0
    lessons = get_all_ingested_lessons()
    return {
        "messages_count": len(message_history),
        "kb_chunks_count": kb_count,
        "chat_archived_count": chat_count,
        "lessons_count": len(lessons),
        "recent_messages": message_history[-20:],
        "ingested_lessons": lessons
    }

@app.get("/api/lessons")
def list_lessons():
    return get_all_ingested_lessons()

@app.post("/ingest/chat-file")
async def ingest_chat_file(
    file: UploadFile = File(...), 
    cohort_tag: str = Form("Cohort 1"),
    group_id: str = Form("cohort_history")
):
    try:
        content_bytes = await file.read()
        raw_text = ""
        
        if file.filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                txt_files = [f for f in z.namelist() if f.endswith(".txt")]
                if not txt_files:
                    raise ValueError("No .txt chat file found inside the uploaded ZIP archive")
                with z.open(txt_files[0]) as txt_f:
                    raw_text = txt_f.read().decode("utf-8", errors="ignore")
        else:
            raw_text = content_bytes.decode("utf-8", errors="ignore")
            
        count = ingest_whatsapp_chat_export_text(raw_text, cohort_tag=cohort_tag, group_id=group_id)
        return {
            "status": "success",
            "filename": file.filename,
            "cohort_tag": cohort_tag,
            "messages_indexed": count
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(payload: WhatsAppWebhookPayload):
    state_input = {
        "sender": payload.sender,
        "group_id": payload.group_id,
        "raw_message": payload.message,
        "classification": None,
        "retrieved_context": None,
        "draft_response": None,
        "should_reply": False
    }
    result = copilot_graph.invoke(state_input)
    
    classification_data = result["classification"].dict() if result.get("classification") else {}
    record = {
        "sender": payload.sender,
        "group_id": payload.group_id,
        "message": payload.message,
        "category": classification_data.get("category", "DIRECT_COMMAND" if payload.is_private else "UNKNOWN"),
        "summary": classification_data.get("summary", ""),
        "deadline": classification_data.get("extracted_deadline"),
        "reply": result.get("draft_response"),
        "should_reply": result.get("should_reply", False),
        "is_private": payload.is_private
    }
    message_history.insert(0, record)
    
    return {
        "status": "processed",
        "category": record["category"],
        "should_reply": record["should_reply"],
        "reply_text": record["reply"],
        "should_alert_prefect": result.get("should_alert_prefect", False),
        "prefect_alert_text": result.get("prefect_alert_text")
    }

@app.post("/ingest/youtube")
async def ingest_youtube_lesson(url: str, title: str = "Bootcamp Lesson", cohort_tag: str = "Cohort 1"):
    try:
        doc = fetch_and_structure_transcript(url, title)
        add_lesson_to_kb(doc, cohort_tag=cohort_tag)
        return {"status": "success", "video_id": doc.video_id, "chunks_added": len(doc.chunks), "title": doc.video_title, "cohort": cohort_tag}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/digest")
def get_digest(cohort: Optional[str] = None):
    context = get_recent_catchup_context(cohort_tag=cohort, n_results=30)
    llm = get_llm()
    prompt = f"""
    You are an executive assistant generating a Catch-Up Digest for a bootcamp prefect.
    Cohort Filter: {cohort or 'All Cohorts'}
    
    Chat Context & Announcements:
    {context}
    
    Generate a clean markdown summary with:
    1. 📢 Major Announcements & Instructor Directives
    2. ⏰ Upcoming Assignments & Deadlines
    3. 🔗 Shared Links, Resources & Colab Notebooks
    4. 💡 Common Student Issues or Discussion Highlights
    """
    return {"cohort": cohort or "All", "digest": llm.invoke(prompt).content}

@app.get("/api/query")
def test_query(q: str, cohort: Optional[str] = None):
    lecture_ctx = query_kb(q, cohort_tag=cohort)
    chat_ctx = query_chat_archive(q, cohort_tag=cohort)
    llm = get_llm()
    prompt = f"""
    Answer the following question using the retrieved knowledge:
    
    Lecture Video Context:
    {lecture_ctx}
    
    Cohort Chat Archive Context:
    {chat_ctx}
    
    Question: {q}
    
    Provide a thorough, structured explanation citing timestamps and links where applicable.
    """
    return {
        "query": q,
        "answer": llm.invoke(prompt).content,
        "lecture_context": lecture_ctx,
        "chat_context": chat_ctx
    }

@app.get("/", response_class=HTMLResponse)
def dashboard_ui():
    kb_count = lesson_collection.count() if lesson_collection else 0
    chat_count = chat_collection.count() if chat_collection else 0
    lessons = get_all_ingested_lessons()
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Cohort Prefect Copilot Dashboard</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
        <style>
            :root {{
                --bg: #071426;
                --panel: #10243d;
                --border: #25425f;
                --text: #eef6ff;
                --muted: #a9bdd3;
                --cyan: #5ee7f7;
                --green: #57df9b;
                --orange: #ffbd66;
                --red: #ff8585;
            }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                background: linear-gradient(135deg, #050d18 0%, #0a1b30 100%);
                color: var(--text);
                min-height: 100vh;
                padding: 24px;
            }}
            .container {{ max-width: 1250px; margin: auto; }}
            header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 1px solid var(--border);
                padding-bottom: 20px;
                margin-bottom: 24px;
            }}
            h1 {{ font-size: 26px; color: var(--cyan); display: flex; align-items: center; gap: 10px; }}
            .badge {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: bold;
                text-transform: uppercase;
            }}
            .badge-live {{ background: rgba(87, 223, 155, 0.15); color: var(--green); border: 1px solid var(--green); }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }}
            .stat-card {{
                background: var(--panel);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 18px;
            }}
            .stat-card .label {{ color: var(--muted); font-size: 13px; margin-bottom: 6px; }}
            .stat-card .val {{ font-size: 28px; font-weight: bold; color: var(--text); }}
            
            .main-grid {{
                display: grid;
                grid-template-columns: 1.1fr 0.9fr;
                gap: 20px;
            }}
            @media (max-width: 900px) {{
                .main-grid {{ grid-template-columns: 1fr; }}
            }}
            .card {{
                background: var(--panel);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
            }}
            .card h2 {{
                font-size: 18px;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                gap: 8px;
                color: var(--cyan);
            }}
            input, select, button {{
                width: 100%;
                padding: 12px;
                margin-bottom: 10px;
                border-radius: 8px;
                border: 1px solid var(--border);
                background: #091728;
                color: #fff;
                font-size: 14px;
            }}
            button {{
                background: #195280;
                color: #fff;
                font-weight: 600;
                cursor: pointer;
                border: none;
                transition: background 0.2s;
            }}
            button:hover {{ background: #236fa8; }}
            .feed {{ max-height: 480px; overflow-y: auto; }}
            .feed-item {{
                background: #091728;
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 14px;
                margin-bottom: 12px;
            }}
            .feed-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 6px;
                font-size: 13px;
            }}
            .sender {{ font-weight: bold; color: var(--cyan); }}
            .category-tag {{
                font-size: 11px;
                padding: 2px 8px;
                border-radius: 4px;
                font-weight: bold;
            }}
            .cat-ANNOUNCEMENT {{ background: #4a3410; color: var(--orange); }}
            .cat-STUDENT_QUESTION {{ background: #133a2a; color: var(--green); }}
            .cat-ASSIGNMENT_DEADLINE {{ background: #421820; color: var(--red); }}
            .cat-DIRECT_COMMAND {{ background: #234d3d; color: var(--green); }}
            .cat-CHITCHAT {{ background: #1c2e42; color: var(--muted); }}
            .bot-reply {{
                margin-top: 10px;
                padding: 10px;
                background: #0f2742;
                border-left: 3px solid var(--green);
                border-radius: 4px;
                font-size: 13px;
            }}
            .lesson-chunk-card {{
                background: #091728;
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 10px;
            }}
            .lesson-chunk-header {{
                display: flex;
                justify-content: space-between;
                font-weight: bold;
                color: var(--cyan);
                margin-bottom: 6px;
            }}
            .links-bar {{ display: flex; gap: 12px; }}
            .links-bar a {{ color: var(--cyan); text-decoration: none; font-size: 14px; }}
            .links-bar a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div>
                    <h1><i class="bi bi-robot"></i> Cohort Prefect Copilot</h1>
                    <p style="color:var(--muted);font-size:14px;margin-top:4px;">Multi-Cohort Knowledge Hub & AI Operations</p>
                </div>
                <div style="text-align:right;">
                    <span class="badge badge-live"><i class="bi bi-broadcast"></i> Live & Listening</span>
                    <div class="links-bar" style="margin-top:8px;">
                        <a href="http://localhost:3000/qr" target="_blank"><i class="bi bi-qr-code"></i> WhatsApp QR</a>
                        <a href="http://localhost:3000/groups" target="_blank"><i class="bi bi-people"></i> Groups</a>
                        <a href="/docs" target="_blank"><i class="bi bi-code-square"></i> API Docs</a>
                    </div>
                </div>
            </header>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="label">Video Chunks (RAG)</div>
                    <div class="val" id="kb-count">{kb_count}</div>
                </div>
                <div class="stat-card">
                    <div class="label">Archived Chat Messages</div>
                    <div class="val" id="chat-count">{chat_count}</div>
                </div>
                <div class="stat-card">
                    <div class="label">Processed Messages</div>
                    <div class="val" id="msg-count">{len(message_history)}</div>
                </div>
                <div class="stat-card">
                    <div class="label">Model Active</div>
                    <div class="val" style="font-size:15px;color:var(--cyan);word-break:break-all;">{settings.OPENROUTER_MODEL}</div>
                </div>
            </div>

            <div class="main-grid">
                <!-- Left: Live WhatsApp Feed & Catch-Up Generator -->
                <div>
                    <div class="card">
                        <h2><i class="bi bi-journal-text"></i> Instant Catch-Up Digest</h2>
                        <div style="display:flex;gap:10px;margin-bottom:10px;">
                            <select id="digest-cohort-select" style="margin-bottom:0;">
                                <option value="">All Cohorts</option>
                                <option value="Cohort 1">Cohort 1</option>
                                <option value="Cohort 2">Cohort 2</option>
                            </select>
                            <button onclick="generateDigest()" style="background:#205e3b;white-space:nowrap;margin-bottom:0;"><i class="bi bi-lightning-fill"></i> Generate Digest</button>
                        </div>
                        <div id="digest-box" style="margin-top:10px;font-size:13px;white-space:pre-wrap;background:#091728;padding:12px;border-radius:6px;border:1px solid var(--border);display:none;max-height:300px;overflow-y:auto;"></div>
                    </div>

                    <div class="card">
                        <h2><i class="bi bi-camera-video-fill"></i> Browse Ingested Video Lectures</h2>
                        <div id="lessons-list" style="max-height:400px;overflow-y:auto;">
                            <p style="color:var(--muted);font-size:13px;">Loading parsed lectures...</p>
                        </div>
                    </div>

                    <div class="card">
                        <h2><i class="bi bi-chat-dots-fill"></i> Live WhatsApp Stream</h2>
                        <p style="color:var(--muted);font-size:13px;margin-bottom:14px;">Real-time feed of cohort chats & private prefect control commands.</p>
                        <div class="feed" id="live-feed">
                            <div style="color:var(--muted);text-align:center;padding:30px;">
                                <i class="bi bi-hourglass-split" style="font-size:24px;"></i>
                                <p style="margin-top:8px;">Listening for cohort messages...</p>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Right: Multi-Cohort Chat Upload, Ingestion & Interactive RAG -->
                <div>
                    <div class="card">
                        <h2><i class="bi bi-search"></i> Interactive Knowledge Base Q&A</h2>
                        <p style="color:var(--muted);font-size:13px;margin-bottom:10px;">Ask any question about your YouTube lectures or chat history:</p>
                        <select id="query-cohort-select">
                            <option value="">All Cohorts</option>
                            <option value="Cohort 1">Cohort 1</option>
                            <option value="Cohort 2">Cohort 2</option>
                        </select>
                        <input type="text" id="query-input" placeholder="e.g. What is the difference between DELETE and TRUNCATE?" />
                        <button onclick="handleQuery()" style="background:#0e402d;"><i class="bi bi-lightning-charge-fill"></i> Query Knowledge Base</button>
                        <div id="query-result" style="margin-top:12px;font-size:13px;white-space:pre-wrap;background:#091728;padding:14px;border-radius:8px;border:1px solid var(--border);display:none;max-height:350px;overflow-y:auto;"></div>
                    </div>

                    <div class="card">
                        <h2><i class="bi bi-file-earmark-zip-fill"></i> Ingest Cohort Chat Export (.ZIP / .TXT)</h2>
                        <form id="chat-upload-form" onsubmit="handleChatUpload(event)">
                            <select id="cohort-tag-select">
                                <option value="Cohort 1">Cohort 1</option>
                                <option value="Cohort 2">Cohort 2</option>
                            </select>
                            <input type="file" id="chat-file" accept=".txt,.zip" required style="padding:8px;" />
                            <button type="submit" id="chat-btn" style="background:#1d4361;"><i class="bi bi-upload"></i> Ingest Chat to Knowledge Base</button>
                        </form>
                        <div id="chat-upload-status" style="margin-top:10px;font-size:13px;"></div>
                    </div>

                    <div class="card">
                        <h2><i class="bi bi-youtube"></i> Ingest YouTube Lesson</h2>
                        <form id="ingest-form" onsubmit="handleIngest(event)">
                            <select id="yt-cohort-select">
                                <option value="Cohort 1">Cohort 1</option>
                                <option value="Cohort 2">Cohort 2</option>
                            </select>
                            <input type="text" id="yt-url" placeholder="https://www.youtube.com/watch?v=..." required />
                            <input type="text" id="yt-title" placeholder="Lesson Title (e.g. SQI Lecture 2)" required />
                            <button type="submit" id="ingest-btn"><i class="bi bi-cloud-arrow-down-fill"></i> Ingest & Chunk Knowledge</button>
                        </form>
                        <div id="ingest-status" style="margin-top:10px;font-size:13px;"></div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            async function refreshFeed() {{
                try {{
                    const res = await fetch('/api/stats');
                    const data = await res.json();
                    
                    document.getElementById('msg-count').innerText = data.messages_count;
                    document.getElementById('kb-count').innerText = data.kb_chunks_count;
                    document.getElementById('chat-count').innerText = data.chat_archived_count;
                    
                    // Render Ingested Lessons
                    if (data.ingested_lessons && data.ingested_lessons.length > 0) {{
                        const list = document.getElementById('lessons-list');
                        list.innerHTML = data.ingested_lessons.map(l => `
                            <div style="margin-bottom:15px;background:#06101d;padding:12px;border-radius:8px;border:1px solid var(--border);">
                                <div style="font-weight:bold;color:var(--cyan);font-size:15px;margin-bottom:4px;">
                                    <i class="bi bi-play-circle-fill" style="color:var(--red);"></i> ${{l.video_title}} <span style="font-size:11px;color:var(--green);">(${{l.cohort_tag}})</span>
                                </div>
                                <div style="font-size:12px;color:var(--muted);margin-bottom:8px;">${{l.chunks.length}} Topic Chunks:</div>
                                ${{l.chunks.map(c => `
                                    <div class="lesson-chunk-card">
                                        <div class="lesson-chunk-header">
                                            <span>${{c.topic}}</span>
                                            <a href="${{c.deep_link}}" target="_blank" style="color:var(--green);text-decoration:none;font-size:12px;"><i class="bi bi-box-arrow-up-right"></i> Play at ${{c.timestamp}}</a>
                                        </div>
                                        <div style="font-size:12px;color:#d9e7f5;margin-bottom:4px;">${{c.content.split('\\nSummary: ')[1] || c.content}}</div>
                                    </div>
                                `).join('')}}
                            </div>
                        `).join('');
                    }}
                    
                    // Render Live Stream
                    if (data.recent_messages && data.recent_messages.length > 0) {{
                        const feed = document.getElementById('live-feed');
                        feed.innerHTML = data.recent_messages.map(m => `
                            <div class="feed-item">
                                <div class="feed-header">
                                    <span class="sender">${{m.sender}} ${{m.is_private ? '<span style="color:#57df9b;">(Private DM)</span>' : ''}}</span>
                                    <span class="category-tag cat-${{m.category}}">${{m.category}}</span>
                                </div>
                                <div style="font-size:14px;margin-bottom:6px;">"${{m.message}}"</div>
                                ${{m.summary ? `<div style="font-size:12px;color:#a9bdd3;"><strong>Summary:</strong> ${{m.summary}}</div>` : ''}}
                                ${{m.deadline ? `<div style="font-size:12px;color:#ff8585;"><strong>Deadline:</strong> ${{m.deadline}}</div>` : ''}}
                                ${{m.reply ? `<div class="bot-reply"><strong>🤖 Bot Reply:</strong><br>${{m.reply}}</div>` : ''}}
                            </div>
                        `).join('');
                    }}
                }} catch (e) {{ console.error(e); }}
            }}

            setInterval(refreshFeed, 3000);
            refreshFeed();

            async function handleChatUpload(e) {{
                e.preventDefault();
                const fileInput = document.getElementById('chat-file');
                const cohortTag = document.getElementById('cohort-tag-select').value;
                const statusDiv = document.getElementById('chat-upload-status');
                const btn = document.getElementById('chat-btn');
                
                if (!fileInput.files[0]) return;
                const formData = new FormData();
                formData.append('file', fileInput.files[0]);
                formData.append('cohort_tag', cohortTag);

                statusDiv.innerHTML = '<span style="color:var(--cyan);">⏳ Parsing chat archive and indexing into ChromaDB...</span>';
                btn.disabled = true;

                try {{
                    const res = await fetch('/ingest/chat-file', {{
                        method: 'POST',
                        body: formData
                    }});
                    const data = await res.json();
                    if (res.ok) {{
                        statusDiv.innerHTML = `<span style="color:var(--green);">✅ Ingested "${{data.filename}}" for ${{data.cohort_tag}}! Indexed ${{data.messages_indexed}} messages.</span>`;
                        fileInput.value = '';
                        refreshFeed();
                    }} else {{
                        statusDiv.innerHTML = `<span style="color:var(--red);">❌ Error: ${{data.detail}}</span>`;
                    }}
                }} catch (err) {{
                    statusDiv.innerHTML = `<span style="color:var(--red);">❌ Upload failed: ${{err.message}}</span>`;
                }} finally {{
                    btn.disabled = false;
                }}
            }}

            async function handleIngest(e) {{
                e.preventDefault();
                const url = document.getElementById('yt-url').value;
                const title = document.getElementById('yt-title').value;
                const cohortTag = document.getElementById('yt-cohort-select').value;
                const statusDiv = document.getElementById('ingest-status');
                const btn = document.getElementById('ingest-btn');
                
                statusDiv.innerHTML = '<span style="color:var(--cyan);">⏳ Downloading transcript & structuring with OpenRouter...</span>';
                btn.disabled = true;

                try {{
                    const res = await fetch(`/ingest/youtube?url=${{encodeURIComponent(url)}}&title=${{encodeURIComponent(title)}}&cohort_tag=${{encodeURIComponent(cohortTag)}}`, {{ method: 'POST' }});
                    const data = await res.json();
                    if (res.ok) {{
                        statusDiv.innerHTML = `<span style="color:var(--green);">✅ Ingested "${{data.title}}" (${{data.cohort}})! Added ${{data.chunks_added}} timestamped chunks.</span>`;
                        document.getElementById('yt-url').value = '';
                        document.getElementById('yt-title').value = '';
                        refreshFeed();
                    }} else {{
                        statusDiv.innerHTML = `<span style="color:var(--red);">❌ Error: ${{data.detail}}</span>`;
                    }}
                }} catch (err) {{
                    statusDiv.innerHTML = `<span style="color:var(--red);">❌ Ingest failed: ${{err.message}}</span>`;
                }} finally {{
                    btn.disabled = false;
                }}
            }}

            async function generateDigest() {{
                const cohort = document.getElementById('digest-cohort-select').value;
                const box = document.getElementById('digest-box');
                box.style.display = 'block';
                box.innerHTML = '<span style="color:var(--cyan);">⏳ Analyzing chat history and generating Catch-Up Digest...</span>';
                try {{
                    const res = await fetch(`/api/digest?cohort=${{encodeURIComponent(cohort)}}`);
                    const data = await res.json();
                    box.innerText = data.digest;
                }} catch (err) {{
                    box.innerText = 'Error generating digest: ' + err.message;
                }}
            }}

            async function handleQuery() {{
                const q = document.getElementById('query-input').value;
                const cohort = document.getElementById('query-cohort-select').value;
                const box = document.getElementById('query-result');
                if (!q) return;
                box.style.display = 'block';
                box.innerHTML = '<span style="color:var(--cyan);">🔍 Querying vector store across lectures and chats...</span>';
                try {{
                    const res = await fetch(`/api/query?q=${{encodeURIComponent(q)}}&cohort=${{encodeURIComponent(cohort)}}`);
                    const data = await res.json();
                    box.innerText = data.answer || 'No matching content found.';
                }} catch (err) {{
                    box.innerText = 'Query error: ' + err.message;
                }}
            }}
        </script>
    </body>
    </html>
    """
