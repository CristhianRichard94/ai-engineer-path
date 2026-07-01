.PHONY: up down restart logs build dev-api dev-worker

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api

logs-worker:
	docker compose logs -f worker

dev-api:
	cd backend && venv/Scripts/python main.py

dev-worker:
	cd backend && venv/Scripts/celery -A worker.app worker --loglevel=info --pool=solo

clean:
	docker compose down -v
