#!/bin/bash
cd ~/TRAIAGENT
source venv/bin/activate
echo "2" | python run_live.py >> logs/startup_$(date +%Y-%m-%d).log 2>&1
