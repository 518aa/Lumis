#!/bin/bash
cd "$(dirname "$0")"
pip install -r requirements.txt -q
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8900 --reload
