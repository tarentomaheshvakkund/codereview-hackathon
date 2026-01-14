#!/bin/bash

LOG_FILE="reindexing.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "Waiting for $LOG_FILE to be created..."
    while [ ! -f "$LOG_FILE" ]; do sleep 1; done
fi

echo "--- Tailing Re-indexing Logs ---"
echo "Press Ctrl+C to stop tailing (process will continue in background)"
echo ""

# Tail the log file in the background
tail -f "$LOG_FILE" &
TAIL_PID=$!

# Trap Ctrl+C to only kill the tail process
trap "kill $TAIL_PID; echo -e '\nStopped tailing.'; exit" INT

wait $TAIL_PID
