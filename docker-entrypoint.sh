#!/bin/bash
set -e

export PYTHONPATH=/app

# Seed agent binaries into the volume on first run (after rebuild).
# The Dockerfile stashes installed agents in /root/.local-seed.
# If the volume is empty (no bin/ dir), copy the seed into the volume.
if [ -d /root/.local-seed ] && [ ! -d /root/.local/bin ]; then
  echo "Seeding agent binaries into volume..."
  cp -a /root/.local-seed/. /root/.local/
  echo "Agent binaries seeded."
fi

# Persist /root/.claude.json across rebuilds by keeping the real file
# inside the /root/.claude volume and symlinking to it.
if [ -f /root/.claude/.claude.json ]; then
  # Volume already has .claude.json from a previous run — just symlink to it.
  # Discard whatever the build image created (it's a fresh empty one).
  rm -f /root/.claude.json
  ln -s /root/.claude/.claude.json /root/.claude.json
  echo "Restored .claude.json symlink from volume."
elif [ -f /root/.claude.json ] && [ ! -L /root/.claude.json ]; then
  # First-ever run: no volume copy yet. Move the file into the volume.
  mv /root/.claude.json /root/.claude/.claude.json
  ln -s /root/.claude/.claude.json /root/.claude.json
  echo "Moved .claude.json into persisted volume."
fi

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
RELOAD_FLAG="${UVICORN_RELOAD:+--reload}"
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 $RELOAD_FLAG
