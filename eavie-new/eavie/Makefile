.PHONY: up down test lint
up: ; cp -n .env.example .env; docker compose up --build -d
down: ; docker compose down
test: ; python -m compileall -q app && python -m pytest -q
lint: ; python -m compileall -q app
