#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [[ -f .runtime/webapp.pid ]]; then
    app_pid="$(<.runtime/webapp.pid)"
    if [[ "$app_pid" == <-> ]] && kill -0 "$app_pid" 2>/dev/null; then
        app_command="$(ps -p "$app_pid" -o command=)"
        if [[ "$app_command" == *neurodb.webapp* ]]; then
            kill "$app_pid"
        fi
    fi
    rm -f .runtime/webapp.pid
fi
if [[ -f .runtime/jupyter.pid ]]; then
    jupyter_pid="$(<.runtime/jupyter.pid)"
    if [[ "$jupyter_pid" == <-> ]] && kill -0 "$jupyter_pid" 2>/dev/null; then
        jupyter_command="$(ps -p "$jupyter_pid" -o command=)"
        if [[ "$jupyter_command" == *"$PWD/.venv/bin/jupyter"* ]]; then
            kill "$jupyter_pid"
        fi
    fi
    rm -f .runtime/jupyter.pid
fi
if [[ -S .runtime/mysql.sock ]]; then
    .venv/bin/python -m neurodb.server stop
fi
print 'NeuroDB stopped. The notebook, project files and ZIP remain on disk.'
