#!/usr/bin/env bash
set -euo pipefail

# Silence a known noisy runtime warning from networkx while preserving all cfn-lint checks.
export PYTHONWARNINGS="ignore:networkx backend defined more than once:RuntimeWarning"

exec /Users/ccs/Library/Python/3.9/bin/cfn-lint "$@"
