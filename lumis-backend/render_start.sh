#!/bin/bash
set -e
echo "=== Testing Python imports ==="
python -c "import app.main; print('import OK')" 2>&1
echo "=== Starting uvicorn ==="
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
