<div align="center">

# Audit Knowledge Assistant
A retrieval-augmented generation chatbot that answers audit and accounting questions. It connects to Confluence, retrieves internal knowledge base and generates the grounded answers with reference sources.

[![Deploy to EC2](https://github.com/Lanting687/RAG/actions/workflows/deploy.yml/badge.svg)](https://github.com/Lanting687/RAG/actions/workflows/deploy.yml)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![React](https://img.shields.io/badge/React-Frontend-blue)
![Docker](https://img.shields.io/badge/Docker-Containerised-blue)
![AWS](https://img.shields.io/badge/AWS-EC2-orange)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-red)
![Gemini](https://img.shields.io/badge/Google-Gemini-yellow)
## Live Demo
[http://auditor_bot.jumpingcrab.com](http://auditor_bot.jumpingcrab.com)

</div>

## Pain Point
- Audit relies on large amounts of internal guidance and technical documentation.
- Finding the right information can take time, especially when it is spread across pages.
- Professionals may spend significant time trying different keywords and opening several documents to find what they need.
- This reduces time available for analysis, review and professional judgement.
## Tech Stack
|Layer|Technology|Purpose|
|---|---|---|
|Frontend|React,Vite|Provides the chat interface|
|Backend|FastAPI,Python|Handles API requests|
|Knowledge Base|Confluence REST API|Retrieves internal documentation|
|Vector Database|Qdrant Cloud|Stores embeddings and performs semantic search|
|Embeddings|Gemini-Embedding-001|Converts questions and document chunks into vectors|
|LLM|Gemini 2.5 Flash|Generates answers using retrieved contents|
|Deployment|AWS EC2 via Docker Compose + GitHub Actions CI/CD|Hosts the containerised app and automates deployment|

## Running Locally
**Prerequisites:** Docker Desktop, a Gemini API key, and a Qdrant Cloud account.

1. Clone the repo
```bash
git clone https://github.com/Lanting687/RAG.git
cd RAG
```

2. Create `backend/.env` with your credentials
```env
GEMINI_API_KEY=your_key
GEMINI_CHAT_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=your_key
GEMINI_EMBEDDINGS_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=your_key
QDRANT_URL=your_qdrant_cloud_url
QDRANT_API_KEY=your_qdrant_api_key
CONFLUENCE_BASE_URL=https://your-domain.atlassian.net/wiki
CONFLUENCE_USERNAME=your_email
CONFLUENCE_API_TOKEN=your_confluence_token
```

3. Create a root `.env` for the frontend
```env
VITE_API_URL=http://localhost:8000
```

4. Build and start
```bash
docker compose up --build
```

5. Open [http://localhost](http://localhost) in your browser



