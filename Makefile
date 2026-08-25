UV ?= uv

.PHONY: setup lock install-hooks test coverage lint format format-check typecheck audit pre-commit check build artifact-check verify clean

setup:
	$(UV) sync --locked --dev

lock:
	$(UV) lock

install-hooks:
	$(UV) run --locked pre-commit install

test:
	$(UV) run --locked pytest

coverage:
	$(UV) run --locked pytest --cov=terminal_intelligence --cov-report=term-missing

lint:
	$(UV) run --locked ruff check .

format:
	$(UV) run --locked ruff format .

format-check:
	$(UV) run --locked ruff format --check .

typecheck:
	$(UV) run --locked mypy

audit:
	$(UV) run --locked pip-audit

pre-commit:
	$(UV) run --locked pre-commit run --all-files

check: format-check lint typecheck test

build:
	rm -rf dist
	$(UV) build --out-dir dist

artifact-check: build
	wheel="$$(printf '%s\n' dist/*.whl)" && sdist="$$(printf '%s\n' dist/*.tar.gz)" && test -f "$$wheel" && test -f "$$sdist"
	tmpdir="$$(mktemp -d)" && trap 'rm -rf "$$tmpdir"' EXIT && wheel="$$(printf '%s\n' "$$(pwd)"/dist/*.whl)" && $(UV) run --isolated --no-project --directory "$$tmpdir" --with "$$wheel" python -c "from terminal_intelligence.domain import UserRequest; assert UserRequest"

verify: check audit pre-commit artifact-check

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov build dist
	rm -rf src/*.egg-info
