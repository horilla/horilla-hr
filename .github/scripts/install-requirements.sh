#!/usr/bin/env bash
# Install requirements.txt for CI without depending on one flaky download.
#
# The spaCy model is not on PyPI; requirements.txt points at a GitHub release
# asset, and that URL has returned HTTP 504 for hours at a time, failing every
# job that installs dependencies. This script:
#   1. downloads the model wheel itself, with a patient retry, into a
#      directory the workflows cache between runs;
#   2. installs everything else from requirements.txt as usual;
#   3. installs the cached wheel.
#
# The model line in requirements.txt stays the single source of truth (the
# URL and version are read from it), so production installs are unchanged.
#
# Usage:
#   install-requirements.sh               install everything
#   install-requirements.sh --filter-only only write the requirements file
#                                         without the model line (for pip-audit)
set -euo pipefail

REQ_FILE="${REQ_FILE:-requirements.txt}"
OUT_DIR="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
FILTERED="$OUT_DIR/requirements-no-model.txt"
CACHE_DIR="${HORILLA_CI_CACHE:-$HOME/.cache/horilla-ci}"

MODEL_LINE_RE='^en_core_web_sm @ '
MODEL_URL="$(grep -E "$MODEL_LINE_RE" "$REQ_FILE" | head -n 1 | sed -E "s/$MODEL_LINE_RE//; s/[[:space:]]+$//")"
if [ -z "$MODEL_URL" ]; then
  echo "No en_core_web_sm line found in $REQ_FILE" >&2
  exit 1
fi

grep -v -E "$MODEL_LINE_RE" "$REQ_FILE" > "$FILTERED"

if [ "${1:-}" = "--filter-only" ]; then
  echo "Wrote $FILTERED"
  exit 0
fi

WHEEL="$CACHE_DIR/$(basename "$MODEL_URL")"
mkdir -p "$CACHE_DIR"

if [ -s "$WHEEL" ]; then
  echo "Using cached model wheel: $WHEEL"
else
  echo "Downloading model wheel: $MODEL_URL"
  # --retry-all-errors is what makes curl retry on a 504, which it does not
  # treat as transient by default.
  curl --fail --location --silent --show-error \
    --retry 8 --retry-all-errors --retry-delay "${CURL_RETRY_DELAY:-15}" \
    --connect-timeout 20 --max-time 120 \
    --output "$WHEEL.part" "$MODEL_URL"
  mv "$WHEEL.part" "$WHEEL"
fi

pip install -r "$FILTERED"
# spaCy comes from the line above; the wheel only needs to be unpacked.
pip install --no-deps "$WHEEL"
