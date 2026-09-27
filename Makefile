.PHONY: install check lint typecheck test eval eval-llm bench production-run docs demo serve clean

BACKEND ?= anthropic

install:
	pip install -e ".[dev]"

check: lint typecheck test

lint:
	ruff check src tests benchmarks docs
	ruff format --check src tests benchmarks docs

typecheck:
	mypy src

test:
	pytest --cov --cov-report=term-missing --cov-fail-under=90

eval:
	for split in test dev injection; do \
		cos eval --split $$split --backend heuristic --no-cache --report reports/heuristic-$$split.md; \
	done

eval-llm:
	for split in test injection; do \
		cos eval --split $$split --backend $(BACKEND) --report reports/$(BACKEND)-$$split.md \
			--json reports/$(BACKEND)-$$split.json; \
	done

bench:
	python benchmarks/bench_latency.py | tee reports/benchmark.md

production-run:
	python benchmarks/production_run.py --report reports/production-run.md

docs:
	python docs/render_assets.py

demo:
	cos run --slack datasets/samples/slack.json --email datasets/samples/email.json \
		--ledger .cos/ledger.sqlite

serve:
	cos serve --host 0.0.0.0 --port 8000

clean:
	rm -rf .cos .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build
