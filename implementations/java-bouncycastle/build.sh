#!/usr/bin/env bash
# Fetch Bouncy Castle provider jar and compile the runner.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
JAR="$ROOT/bcprov.jar"
VER="1.78.1"
URL="https://repo1.maven.org/maven2/org/bouncycastle/bcprov-jdk18on/${VER}/bcprov-jdk18on-${VER}.jar"
OUT="$ROOT/out"

if [[ ! -f "$JAR" ]]; then
  curl -fsSL -o "$JAR" "$URL"
fi
mkdir -p "$OUT"
javac -cp "$JAR" -d "$OUT" "$ROOT/Sha256Runner.java"
echo "built java-bouncycastle"
