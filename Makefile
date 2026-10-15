PYTHON ?= .venv/bin/python
.PHONY: setup test lint audit cluster images demo integration incident drift
setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
test:
	$(PYTHON) -m unittest discover -s tests -v
	cd sample && go test -race ./... && go vet ./...
lint:
	$(PYTHON) -m ruff check releaseguard tests scripts
	$(PYTHON) -m ruff format --check releaseguard tests scripts
	@test -z "$$(gofmt -l sample)"
audit:
	$(PYTHON) -m pip_audit -r requirements.txt
cluster:
	$(PYTHON) -m releaseguard cluster
images:
	PYTHONPATH=. $(PYTHON) scripts/images.py
demo:
	$(PYTHON) -m releaseguard bootstrap
	$(PYTHON) -m releaseguard baseline
integration:
	PYTHONPATH=. $(PYTHON) scripts/integration.py
incident: integration
	@cat .local/integration/incident$(ID).json
drift:
	$(PYTHON) -m releaseguard drift
