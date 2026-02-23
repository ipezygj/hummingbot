#!/bin/bash
# Käyttö: ./pusku.sh "viestisi tähän"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "🚀 Aloitetaan automaattinen pusku haarasta: $BRANCH"

git add .
git commit -m "$1"
git push origin $BRANCH --force

echo "✅ Valmis! Tarkista GitHub: https://github.com/ipezygj/hummingbot"
