#!/usr/bin/env bash
# Downloads the solc compiler binary used by py/compile.py.
# Pulled directly from the ethereum/solidity GitHub releases page rather
# than binaries.soliditylang.org, which isn't reachable from every
# network (it wasn't from the sandbox this repo was built in).
set -euo pipefail
VERSION="${1:-0.8.24}"
URL="https://github.com/ethereum/solidity/releases/download/v${VERSION}/solc-static-linux"
curl -sL -o "$(dirname "$0")/solc" "$URL"
chmod +x "$(dirname "$0")/solc"
echo "solc v${VERSION} installed at tools/solc"
