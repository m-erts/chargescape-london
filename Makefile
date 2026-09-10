PY ?= python3
export PYTHONPATH := src

.PHONY: help install data features models maps test lint notebooks clean

help:
	@echo "install   - pip install -e .[dev]"
	@echo "data      - download all raw/interim data (idempotent)"
	@echo "features  - build the H3 feature table"
	@echo "models    - run demand, choice, queue and siting pipelines"
	@echo "maps      - export interactive maps to reports/maps and docs/maps"
	@echo "test/lint - pytest / ruff"

install:
	pip install -e ".[dev]"

data:
	$(PY) -m chargescape.data.census
	$(PY) -m chargescape.data.vehicles
	$(PY) -m chargescape.data.chargepoints
	$(PY) -m chargescape.data.osm
	$(PY) -m chargescape.data.transit
	$(PY) -m chargescape.data.traffic
	$(PY) -m chargescape.data.weather
	$(PY) -m chargescape.data.ukpn
	$(PY) -m chargescape.data.sessions_open

features:
	$(PY) -m chargescape.features.build

models:
	$(PY) -m chargescape.models.run_all

maps:
	$(PY) -m chargescape.viz.export_maplibre
	$(PY) scripts/make_slides.py

test:
	$(PY) -m pytest -q

lint:
	ruff check src tests

clean:
	rm -rf data/interim/* data/processed/*.parquet reports/figures/* reports/maps/*.html
