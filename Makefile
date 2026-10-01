.PHONY: install check lint typecheck test eval eval-llm bench production-run scale docs site demo serve clean

BACKEND ?= nvidia
MODEL ?=
TAG ?= $(BACKEND)

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
	for split in test dev injection external; do \
		cos eval --split $$split --backend heuristic --no-cache --report reports/heuristic-$$split.md \
			--json reports/heuristic-$$split.json; \
	done

# Live evaluation. The per-run cache makes it resumable: rerun the same command after a rate
# limit and only the missing answers are requested. Delete the cache file for a fresh run.
eval-llm:
	for split in test injection external; do \
		cos eval --split $$split --backend $(BACKEND) $(if $(MODEL),--model $(MODEL)) \
			--cache .cos/runs/$(TAG).sqlite --report reports/$(TAG)-$$split.md \
			--json reports/$(TAG)-$$split.json || exit 1; \
	done

bench:
	python benchmarks/bench_latency.py | tee reports/benchmark.md

production-run:
	python benchmarks/production_run.py --report reports/production-run.md

scale:
	python benchmarks/scale_run.py --report reports/scale-run.md

docs:
	python docs/render_assets.py

site:
	python docs/build_site.py --out site

demo:
	cos run --slack datasets/samples/slack.json --email datasets/samples/email.json \
		--ledger .cos/ledger.sqlite

serve:
	cos serve --host 0.0.0.0 --port 8000

clean:
	rm -rf .cos .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build
