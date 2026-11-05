#!/usr/bin/env bash
# Reproduces every number, table and figure in the README from scratch.
set -euo pipefail
cd "$(dirname "$0")"
python data/generate.py
python -m src.power
python -m src.analyze
python -m src.report
jupyter nbconvert --to notebook --execute --inplace notebooks/01_analysis.ipynb --ExecutePreprocessor.timeout=600
echo "done: see README.md and results/"
