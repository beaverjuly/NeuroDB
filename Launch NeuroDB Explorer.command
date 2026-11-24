#!/bin/zsh
set -e
cd "$(dirname "$0")"
if curl --silent --fail http://127.0.0.1:8765/health >/dev/null 2>&1; then
    open http://127.0.0.1:8765/
    exit 0
fi
.venv/bin/python -m neurodb.webapp --port 8765 &
app_pid=$!
for i in {1..120}; do
    if curl --silent --fail http://127.0.0.1:8765/health >/dev/null 2>&1; then
        open http://127.0.0.1:8765/
        wait $app_pid
        exit $?
    fi
    sleep 1
done
print -u2 'NeuroDB Explorer did not start. Check the messages above.'
wait $app_pid
