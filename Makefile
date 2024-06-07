# Any args passed to the make script, use with $(call args, default_value)
args = `arg="$(filter-out $@,$(MAKECMDGOALS))" && echo $${arg:-${1}}`

########################################################################################################################
# Quality checks
########################################################################################################################

test:
	PYTHONPATH=. poetry run pytest tests

test-coverage:
	PYTHONPATH=. poetry run pytest tests --cov sonar_labs --cov-report term --cov-report=html --cov-report xml --junit-xml=tests-results.xml

black:
	poetry run black . --check

ruff:
	poetry run ruff check sonar_labs tests

format:
	poetry run black .
	poetry run ruff check sonar_labs tests --fix

mypy:
	poetry run mypy sonar_labs

check:
	make format
	make mypy

########################################################################################################################
# Run
########################################################################################################################

run:
	poetry run python -m sonar_labs

dev-windows:
	(set SONAR_PROFILES=local & poetry run python -m uvicorn sonar_labs.main:app --reload --port 8001)

dev:
	PYTHONUNBUFFERED=1 SONAR_PROFILES=local poetry run python -m uvicorn sonar_labs.main:app --reload --port 8001

prod:
	PYTHONUNBUFFERED=1 SONAR_PROFILES=openai poetry run python -m uvicorn sonar_labs.main:app --workers 4 --port 8001

########################################################################################################################
# Misc
########################################################################################################################

api-docs:
	SONAR_PROFILES=mock poetry run python scripts/extract_openapi.py sonar_labs.main:app --out fern/openapi/openapi.json

ingest:
	@poetry run python scripts/ingest_folder.py $(call args)

stats:
	poetry run python scripts/utils.py stats

wipe:
	poetry run python scripts/utils.py wipe

setup:
	poetry run python scripts/setup

list:
	@echo "Available commands:"
	@echo "  test            : Run tests using pytest"
	@echo "  test-coverage   : Run tests with coverage report"
	@echo "  black           : Check code format with black"
	@echo "  ruff            : Check code with ruff"
	@echo "  format          : Format code with black and ruff"
	@echo "  mypy            : Run mypy for type checking"
	@echo "  check           : Run format and mypy commands"
	@echo "  run             : Run the application"
	@echo "  dev-windows     : Run the application in development mode on Windows"
	@echo "  dev             : Run the application in development mode"
	@echo "  api-docs        : Generate API documentation"
	@echo "  ingest          : Ingest data using specified script"
	@echo "  wipe            : Wipe data using specified script"
	@echo "  setup           : Setup the application"
