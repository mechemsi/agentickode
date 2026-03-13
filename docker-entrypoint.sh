#!/bin/bash
set -e

export PYTHONPATH=/app

# Auto-generate SSH key if missing
SSH_DIR="/app/.ssh"
DEFAULT_KEY="$SSH_DIR/id_ed25519"
if [ ! -f "$DEFAULT_KEY" ]; then
  echo "Generating default SSH key at $DEFAULT_KEY..."
  mkdir -p "$SSH_DIR"
  ssh-keygen -t ed25519 -f "$DEFAULT_KEY" -N "" -C "agentickode@$(hostname)"
  chmod 600 "$DEFAULT_KEY"
  chmod 644 "$DEFAULT_KEY.pub"
  echo "SSH key generated."
fi

echo "Running database migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
