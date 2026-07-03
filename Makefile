.PHONY: check lint test run

check: lint test

lint:
	ruff check .

test:
	python -m pytest -q

run:
	uvicorn app.main:app --reload
