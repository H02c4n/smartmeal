# SmartMeal developer shortcuts. Everything runs inside Docker Compose.
COMPOSE ?= docker compose
RUN := $(COMPOSE) run --rm backend

.DEFAULT_GOAL := help
.PHONY: help setup build up down logs ps migrate makemigrations superuser shell dbshell test lint format check schema reset-db

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

setup: ## Create .env from .env.example (if missing)
	@test -f .env && echo ".env already exists" || (cp .env.example .env && echo "Created .env - now set DJANGO_SECRET_KEY and POSTGRES_PASSWORD")

build: ## Build the backend image
	$(COMPOSE) build

up: ## Start db + backend in the background
	$(COMPOSE) up -d

down: ## Stop containers (data volume is kept)
	$(COMPOSE) down

logs: ## Follow logs
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

migrate: ## Apply database migrations
	$(RUN) python manage.py migrate

makemigrations: ## Create new migrations
	$(RUN) python manage.py makemigrations

superuser: ## Create a Django superuser (interactive)
	$(RUN) python manage.py createsuperuser

shell: ## Django shell
	$(RUN) python manage.py shell

dbshell: ## psql inside the db container
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

test: ## Run the test suite
	$(RUN) pytest

lint: ## Lint + format check (no changes)
	$(RUN) sh -c "ruff check . && ruff format --check ."

format: ## Auto-fix lint issues and format code
	$(RUN) sh -c "ruff check . --fix && ruff format ."

check: ## Same checks CI runs: lint, migration drift, OpenAPI schema, tests
	$(RUN) sh -c "ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python manage.py spectacular --validate --fail-on-warn --file /dev/null && pytest"

schema: ## Write the OpenAPI schema to backend/openapi.yml
	$(RUN) python manage.py spectacular --validate --fail-on-warn --file openapi.yml

reset-db: ## DANGER: delete the local database volume and start fresh
	@printf "This deletes ALL local database data. Type yes to continue: " && read ans && [ "$$ans" = "yes" ]
	$(COMPOSE) down -v
