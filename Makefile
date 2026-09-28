.PHONY: data extract evaluate test lint

data:
	uv run invoice-extraction corpus
	uv run invoice-extraction groundtruth

extract:
	uv run invoice-extraction extract

evaluate:
	uv run invoice-extraction evaluate

test:
	uv run pytest -q

lint:
	uv run ruff check src tests
