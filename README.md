# EAVIE — Enterprise Agentic Vision Intelligence Engine
Backend (FastAPI/LangGraph/CNN/Celery/Docker) + `site/` (GitHub Pages showcase with Groq assistant).
## Run backend
cp .env.example .env && docker compose up --build   
## Deploy site (GitHub Pages)
Push repo to GitHub -> Settings > Pages > Source: GitHub Actions. Workflow `.github/workflows/pages.yml` publishes `site/`.
Chatbot: paste free Groq key (console.groq.com) in the widget; stored in browser only.
