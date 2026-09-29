PY ?= python3
export PYTHONPATH := src

.PHONY: help install data features models report maps slides notebooks quick all test lint serve clean

help:
	@echo "Quick path (from the committed tables in data/processed; the MILPs take ~1 h):"
	@echo "  make install      pip install -e .[all]"
	@echo "  make models       demand (Monte Carlo) -> choice + queues -> siting MILP -> sensitivity"
	@echo "  make report maps slides notebooks"
	@echo "Full rebuild from open sources (~4 GB downloads, ~2 h):"
	@echo "  make data features models report maps slides notebooks   (= make all)"
	@echo "Other: make test | lint | serve (docs site on http://localhost:8000)"

install:
	pip install -e ".[all]"

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
	$(PY) -m chargescape.features.build --res 8
	$(PY) -m chargescape.features.station_context --quiet

models:
	$(PY) -m chargescape.models.demand_pipeline --res 8
	$(PY) -m chargescape.models.allocation_pipeline --scenario 2026
	$(PY) -m chargescape.optimize.siting_pipeline --scenario 2026 --budgets 5,10,20,40
	$(PY) -m chargescape.optimize.sensitivity --budget 20

report:
	$(PY) scripts/key_numbers.py
	$(PY) scripts/update_readme_numbers.py
	$(PY) scripts/build_catalog.py

maps:
	$(PY) -m chargescape.viz.export_maplibre

slides:
	$(PY) scripts/make_hero.py
	$(PY) scripts/make_site.py
	$(PY) scripts/make_slides.py
	$(PY) scripts/make_deck.py

notebooks:
	$(PY) scripts/make_notebooks.py --force
	jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1800 notebooks/*.ipynb

quick: report maps slides notebooks

all: data features models report maps slides notebooks

test:
	$(PY) -m pytest -q

lint:
	ruff check src tests scripts
	ruff format --check src tests scripts

serve:
	$(PY) -m http.server 8000 --directory docs

clean:
	rm -rf data/interim/* reports/maps/*.html
