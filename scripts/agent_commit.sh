#!/bin/bash

git add .

if ! git diff --cached --quiet; then
    git commit -m "agent update $(date '+%Y-%m-%d %H:%M')"
    git push origin dev
fi
