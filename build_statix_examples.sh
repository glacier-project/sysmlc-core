#!/usr/bin/env bash

set -u

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <models-folder-or-corpus-name>" >&2
  echo "Example: $0 sm-examples" >&2
  exit 1
fi

MODEL_ROOT="$1"
OUTPUT_ROOT="output"

# A non-directory argument names a bundled corpus (e.g. sm-examples):
# resolve it through the installed sysmlc-models package, like the CLI does.
if [ ! -d "$MODEL_ROOT" ]; then
  MODEL_ROOT="$(uv run --extra dev python -c "
from sysmlc_models.catalog import model_path
print(model_path('$1'))
" 2>/dev/null)" || true
fi

if [ ! -d "$MODEL_ROOT" ]; then
  echo "error: neither a folder nor a bundled corpus: $1" >&2
  exit 1
fi

mkdir -p "$OUTPUT_ROOT"

ls -1 "$MODEL_ROOT" | while IFS= read -r name; do
  model="$MODEL_ROOT/$name"

  [ -d "$model" ] || continue

  out="$OUTPUT_ROOT/$name"

  cmd=(uv run --extra dev sysmlc statix build "$model" --out "$out")

  printf '\n$'
  printf ' %q' "${cmd[@]}"
  printf ' 2>&1 | grep -i error\n'

  "${cmd[@]}" 2>&1 | grep -i error || true
done
