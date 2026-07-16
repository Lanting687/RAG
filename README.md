# Audit Knowledge Assistant
A retrieval-augmented generation chatbot that answers audit and accounting questions. It connects to Confluence, retrieves internal knowledge base and generates the grounded answers with reference sources. 
## Pain Point
- Audit relies on large amounts of internal guidance and technical documentation.
- Finding the right information can take time, especially when it is spread across pages.
- Professionals may spend significant time tring different keywords and opening serveral documents to find what they need. 
- This reduces time available for analysis, review and professional judgement.
## Tech Stack
|Layer|Technology|Purpose|
|---|---|---|
|Frontend|React,Vite|Provides the chat interface|
|Backend|FastAPI,Python|Handles API requests|
|Knowledge Base|Confluence REST API|Retreives internal documentation|
|Vector Database|Qdrant Cloud|Stores embeddings and performs semantic search|
|Embeddings|Gemini-Embedding-001|Converts questions and document chunks into vectors|
|LLM|Gemini 2.5 Flash|Generates answers using retrieved contents|
|Deployment|AWS EC2 via Docker Compose + GitHub Actions CI/CD|Hosts the containerised app and automates deployment|



