UV ?= uv
COVERAGE_MIN ?= 80
COVERAGE_SOURCES = agents clients config main observability pipeline tools utils
COVERAGE_ARGS = $(foreach source,$(COVERAGE_SOURCES),--cov=$(source))

.PHONY: validate

validate:
	$(UV) sync --frozen --extra dev
	$(UV) lock --check
	$(UV) run ruff check .
	$(UV) run python -m pytest -q $(COVERAGE_ARGS) --cov-report=term-missing --cov-fail-under=$(COVERAGE_MIN)
	@echo "VALIDATE APROVADO: Ruff sem findings; testes aprovados; cobertura >= $(COVERAGE_MIN)%"
