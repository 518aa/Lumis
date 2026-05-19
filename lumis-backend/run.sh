#!/bin/bash
cd "$(dirname "$0")"

# 加载环境变量
if [ -f .env.alipay ]; then
    set -a
    source .env.alipay
    set +a
fi

pip install -r requirements.txt -q
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8900 --reload
