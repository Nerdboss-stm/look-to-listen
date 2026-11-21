#!/usr/bin/env bash
# Pod side. Starts the separation server on 127.0.0.1:8000 and restarts it if it dies. Safe to run twice.
# On the pod: nohup bash /workspace/clearvoice_home/run_separator.sh >/dev/null 2>&1 &
exec 9>/workspace/separator.lock
flock -n 9 || { echo "already running"; exit 0; }
cd /workspace/clearvoice_home || exit 1
set -a; . ./separator.env; set +a
while true; do
  echo "$(date -u +%H:%M:%S) starting server" >> /workspace/separator.log
  python -u separator_server.py >> /workspace/separator.log 2>&1
  echo "$(date -u +%H:%M:%S) server exited with code $?; restarting in 2 s" >> /workspace/separator.log
  sleep 2
done
