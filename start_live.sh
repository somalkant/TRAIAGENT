#!/bin/bash
cd ~/TRAIAGENT
source venv/bin/activate
exec python run_live.py "$@"
