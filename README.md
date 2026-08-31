# WhatsApp & YouTube Cohort Copilot 🚀

A dual-role AI Copilot for bootcamp prefects and students built with **LangGraph**, **OpenRouter**, **YouTube Transcript API**, and **Baileys**.

---

## Architecture Overview
- **YouTube Knowledge Ingestion**: Downloads lesson transcripts, breaks them down into conceptual chunks with start timestamps, and stores them in ChromaDB.
- **Free WhatsApp Listener Bridge**: Uses `@whiskeysockets/baileys` to link your WhatsApp account via QR code for $0 API cost.
- **LangGraph State Router**: Classifies incoming chat messages:
  - *Announcements & Deadlines* $\rightarrow$ Logged to prefect catch-up digest.
  - *Student Questions* $\rightarrow$ Answers drafted using RAG with deep YouTube timestamp citations.
- **Cloud Run Deployment**: Serverless deployment with auto-scale to 0 for **$0.00** monthly hosting.

---

## Quick Start

### 1. Python LangGraph Backend
```bash
# Navigate to project directory
cd WhatsApp-Cohort-Copilot

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Run FastAPI backend
uvicorn src.api:app --reload --port 8080
```

### 2. WhatsApp Listener Bridge
```bash
# Navigate to bridge directory
cd bridge

# Install Node dependencies
npm install

# Start bridge
npm start
```
Open **http://localhost:3000/qr** in your browser, open WhatsApp on your phone $\rightarrow$ **Linked Devices** $\rightarrow$ **Link a Device**, and scan the QR code!

---

## Running Tests
```bash
pytest tests/ -v
```
