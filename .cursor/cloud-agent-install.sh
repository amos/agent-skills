#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! python3 -c "import yaml" 2>/dev/null; then
  pip3 install --user --quiet pyyaml
fi

python3 "$ROOT/.cursor/validate-skills.py"
