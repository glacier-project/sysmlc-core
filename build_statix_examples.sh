#!/usr/bin/env bash

set -u

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <models-folder>" >&2
  echo "Example: $0 models/sm-examples" >&2
  exit 1
fi

MODEL_ROOT="$1"
OUTPUT_ROOT="output"

if [ ! -d "$MODEL_ROOT" ]; then
  echo "error: folder does not exist: $MODEL_ROOT" >&2
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
