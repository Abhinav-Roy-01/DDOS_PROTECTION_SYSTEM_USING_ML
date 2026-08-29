.PHONY: setup dev build test lint clean seed train shield shield-test shield-attack

setup:
	cp .env.example .env
	pip install poetry
	poetry install
	pip install -r HTTP-LAYER-SHIELD/API/requirements.txt
	cd DASHBOARD && npm install

dev:
	docker-compose up redis timescaledb -d
	poetry run uvicorn API.main:app --reload --port 8000 &
	cd DASHBOARD && npm run dev

# --- HTTP-LAYER-SHIELD (merged legacy behavioral shield) ---
shield:
	cd HTTP-LAYER-SHIELD/API && python server.py

shield-test:
	python HTTP-LAYER-SHIELD/TESTS/test_predictions.py

shield-attack:
	python HTTP-LAYER-SHIELD/TESTS/attacker.py

build:
	docker-compose build

test:
	poetry run pytest TESTS/UNIT -v
	poetry run pytest TESTS/INTEGRATION -v

lint:
	poetry run ruff check .
	poetry run black --check .
	poetry run mypy .

seed:
	poetry run python SCRIPTS/SEED/generate_dataset.py
	poetry run python ML/TRAINING/train.py

train:
	poetry run python ML/TRAINING/train.py

benchmark:
	poetry run python SCRIPTS/BENCHMARK/latency_test.py

clean:
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} +
