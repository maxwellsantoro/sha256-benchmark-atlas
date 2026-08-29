#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
dotnet publish -c Release -o out
# Stable path for the registry binary field.
cp -f out/sha256_runner ./sha256_runner 2>/dev/null || cp -f out/sha256_runner.dll ./sha256_runner.dll
# Prefer the native apphost when present.
if [[ -f out/sha256_runner ]]; then
  ln -sfn out/sha256_runner sha256_runner
elif [[ -f out/sha256_runner.dll ]]; then
  cat > sha256_runner <<'EOF'
#!/usr/bin/env bash
exec dotnet "$(dirname "$0")/out/sha256_runner.dll" "$@"
EOF
  chmod +x sha256_runner
fi
