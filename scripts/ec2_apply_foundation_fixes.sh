#!/bin/bash
# Apply the 2026-09-19 foundation fixes on the EC2 box (run from ~/TRAIAGENT after ec2-deploy is pushed).
#   bash scripts/ec2_apply_foundation_fixes.sh            # does everything below
# Safe to re-run. Paper trading stays paused (the TRAIAGENT @reboot cron line is commented out).
set -euo pipefail
cd ~/TRAIAGENT
B=s3://amzn-s3-somal-bucket-mumbai/traiagent
STAMP=$(date +%Y%m%d_%H%M)

echo "== 1. back up every data file to S3 before touching anything"
aws s3 sync data "$B/backup_pre_repair_$STAMP/data" --only-show-errors --region ap-south-1

echo "== 2. update code, keeping EC2's own (newer) data files"
git stash push -m "ec2-data-$STAMP" -- data/index/2026 data/trade_logs/live_paper_trades.csv || true
git pull --ff-only origin ec2-deploy
if git stash list | grep -q "ec2-data-$STAMP"; then
  git checkout "stash@{0}" -- data/index/2026 data/trade_logs/live_paper_trades.csv
  git stash drop
fi

source venv/bin/activate
echo "== 3. repair all years; re-download the days the old +5:30 bug overwrote (needs the Groww API)"
python scripts/repair_parquet_data.py --redownload --broker groww
echo "== 4. 2026 only: also re-fetch days with <70 bars"
python scripts/repair_parquet_data.py --years 2026 --redownload --include-short-days --broker groww
echo "== 5. verify: expect 0 tz-aware, 0 out-of-session, 0 corrupt afternoons"
python scripts/repair_parquet_data.py --dry-run | tail -4
echo "== 6. unit tests for the new data format and official-candle reconciliation"
python -m pytest tests/test_official_bars.py -q
echo "== 7. publish the repaired data for the analysis machine"
aws s3 sync data/stocks "$B/analysis_sync_2026-09-19/data/stocks" --only-show-errors --region ap-south-1
aws s3 sync data/index  "$B/analysis_sync_2026-09-19/data/index"  --only-show-errors --region ap-south-1
echo "done. backup at $B/backup_pre_repair_$STAMP/"
