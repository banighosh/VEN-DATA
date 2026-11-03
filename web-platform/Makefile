.PHONY: up down logs test api web typecheck

up:        ## build and start the full stack
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f api web
test:      ## backend tests (set TEST_DATABASE_URL for PostgreSQL, ADIDAS_XLSX for dataset checks)
	cd backend && pytest
api:       ## run the API locally with reload
	cd backend && uvicorn app.main:app --reload --port 8000
web:       ## run the frontend dev server (proxies /api to :8000)
	cd frontend && npm install && npm run dev
typecheck:
	cd frontend && npm run typecheck
