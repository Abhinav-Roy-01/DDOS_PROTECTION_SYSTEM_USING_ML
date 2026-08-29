#!/bin/bash
set -e
echo "[1/6] Copying env file..."
cp .env.example .env
echo "[2/6] Installing Python deps..."
pip install poetry && poetry install
echo "[3/6] Installing HTTP-layer shield deps..."
pip install -r HTTP-LAYER-SHIELD/API/requirements.txt
echo "[4/6] Installing dashboard deps..."
cd DASHBOARD && npm install && cd ..
echo "[5/6] Starting infrastructure..."
docker-compose up redis timescaledb -d
sleep 4
echo "[6/6] Running migrations..."
poetry run python SCRIPTS/MIGRATE/run_migrations.py
echo "Done. Run: make seed then make dev"
