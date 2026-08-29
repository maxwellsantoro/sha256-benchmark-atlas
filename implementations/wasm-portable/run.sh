#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec wasmtime run "$HERE/sha256_runner.wasm" "$@"
