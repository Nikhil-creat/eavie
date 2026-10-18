# EAVIE — Enterprise Agentic Vision Intelligence Engine
Designed & developed by **Nikhil Chary Sriramoju**. MIT licensed. See `docs/ARCHITECTURE.md`, `SECURITY.md`, `CONTRIBUTING.md`.

- Live site: https://nikhil-creat.github.io/eavie/
- Backend: FastAPI, LangGraph, hybrid RAG, PyTorch CNN, Celery, Redis, Postgres, Prometheus (`docker compose up --build` after `cp .env.example .env`)
- Site: `site/` is deployed by `.github/workflows/pages.yml` (Settings > Pages > Source: GitHub Actions)
- Chatbot: paste a free Groq key from console.groq.com into the widget (stored in your browser only)
