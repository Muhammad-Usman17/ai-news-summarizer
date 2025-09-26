# Makefile for AI News Summarizer

.PHONY: help dev-up dev-down dev-logs prod-up prod-down prod-logs install test lint format clean

# Default target
help:
	@echo "Available commands:"
	@echo "  dev-setup      - Set up development environment"
	@echo "  dev-up         - Start development dependencies"
	@echo "  dev-down       - Stop development dependencies"
	@echo "  dev-logs       - Show development logs"
	@echo "  dev-run-api    - Run FastAPI service locally"
	@echo "  dev-run-worker - Run Celery worker locally (concurrency=2)"
	@echo "  dev-run-beat   - Run Celery beat scheduler locally"
	@echo "  dev-run-temporal - Run Temporal worker locally"
	@echo "  prod-build     - Build production containers"
	@echo "  prod-up        - Start production services"
	@echo "  prod-down      - Stop production services"
	@echo "  prod-logs      - Show production logs"
	@echo "  install        - Install Python dependencies"
	@echo "  test           - Run tests"
	@echo "  lint           - Run linting"
	@echo "  format         - Format code"
	@echo "  clean          - Clean up containers and volumes"
	@echo "  db-upgrade     - Run database migrations"
	@echo "  db-downgrade   - Rollback database migrations"

# Development Environment
dev-setup:
	@echo "Setting up development environment..."
	cp .env.example .env
	pip3 install -r requirements.txt
	@echo "Development environment ready!"

dev-up:
	@echo "Starting development dependencies..."
	docker compose -f docker-compose.dev.yml up -d
	@echo "Waiting for services to be ready..."
	sleep 30
	@echo "Development dependencies started!"

dev-down:
	@echo "Stopping development dependencies..."
	docker compose -f docker-compose.dev.yml down

dev-logs:
	docker compose -f docker-compose.dev.yml logs -f

# Local Development Services
dev-run-api:
	@echo "Starting FastAPI service locally..."
	python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-run-worker:
	@echo "Starting Celery worker locally with concurrency=2..."
	python3 -m celery -A app.celery_app worker --loglevel=info --concurrency=2

dev-run-beat:
	@echo "Starting Celery beat scheduler with auto-restart watchdog..."
	python3 scripts/celery_beat_watchdog.py

dev-run-beat-simple:
	@echo "Starting Celery beat scheduler locally..."
	python3 -m celery -A app.celery_app beat --loglevel=info

dev-run-temporal:
	@echo "Starting Temporal worker locally..."
	python3 -m app.workflows.temporal_worker

# Production Environment
prod-build:
	@echo "Building production containers..."
	docker compose -f docker-compose.prod.yml build

prod-up:
	@echo "Starting production services..."
	docker compose -f docker-compose.prod.yml up -d
	@echo "Production services started!"

prod-down:
	@echo "Stopping production services..."
	docker compose -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f

# Python Dependencies
install:
	@echo "Installing Python dependencies..."
	pip3 install -r requirements.txt

# Testing and Quality
test:
	@echo "Running tests..."
	python3 -m pytest tests/ -v

lint:
	@echo "Running linting..."
	python3 -m flake8 app/
	python3 -m isort --check-only app/

format:
	@echo "Formatting code..."
	python3 -m black app/
	python3 -m isort app/

# Database Operations
db-upgrade:
	@echo "Running database migrations..."
	python3 -m alembic upgrade head

db-downgrade:
	@echo "Rolling back database migrations..."
	python3 -m alembic downgrade -1

# Cleanup
clean:
	@echo "Cleaning up..."
	docker compose -f docker-compose.dev.yml down -v
	docker compose -f docker-compose.prod.yml down -v
	docker system prune -f

# Monitoring
monitor:
	@echo "Opening monitoring dashboards..."
	@echo "Grafana: http://localhost:3000 (admin/admin)"
	@echo "Jaeger: http://localhost:16686"
	@echo "Prometheus: http://localhost:9090"
	@echo "Temporal Web: http://localhost:8080"

# Development Workflow
dev: dev-setup dev-up
	@echo "Development environment is ready!"
	@echo "Run 'make dev-run-api' in another terminal to start the API"
	@echo "Run 'make dev-run-worker' in another terminal to start Celery"
	@echo "Run 'make dev-run-temporal' in another terminal to start Temporal worker"
	@echo "Run 'make dev-run-hourly' in another terminal to start automatic scheduled processing"