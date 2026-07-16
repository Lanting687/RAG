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



