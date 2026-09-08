# Convenience only. Every target is a plain Python entry point that also runs
# unchanged on Windows PowerShell without make.
.PHONY: install lint format typecheck test check text-smoke naming

install:
	uv pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src

test:
	pytest -q

naming:
	python -m faultline.cli check naming

check: lint typecheck test naming

text-smoke:
	python scripts/run_text_stage.py --config configs/data/text_v0.yaml --stage all --input tests/fixtures/text/sample.jsonl
