#!/bin/bash
set -e

echo "Updating repository..."
git pull origin dev

echo "Restarting services..."

if command -v docker >/dev/null 2>&1; then
    docker compose down || true
    docker compose up -d --build
fi

echo "Deploy complete."
