.PHONY: run test clean
PYTHON ?= python
run:
	$(PYTHON) src/depgraph.py $(ARGS)
test:
	$(PYTHON) -m pytest tests/ -v
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true