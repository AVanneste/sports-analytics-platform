#!/usr/bin/env bash
# ==============================================================================
# Master Sports Analytics Platform — Automated Daily Pipeline Runner
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/daily_pipeline_$(date +'%Y%m%d').log"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

mkdir -p "${LOG_DIR}"

echo "======================================================================" >> "${LOG_FILE}"
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting Automated Daily Pipeline" >> "${LOG_FILE}"
echo "======================================================================" >> "${LOG_FILE}"

cd "${PROJECT_ROOT}"

if [ ! -f "${VENV_PYTHON}" ]; then
    echo "ERROR: Python virtual environment not found at ${VENV_PYTHON}" >> "${LOG_FILE}"
    exit 1
fi

export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/Football:${PROJECT_ROOT}/Tennis:${PROJECT_ROOT}/scripts:${PYTHONPATH:-}"

# Execute daily pipeline and append output to log
"${VENV_PYTHON}" "${PROJECT_ROOT}/scripts/run_daily_pipeline.py" >> "${LOG_FILE}" 2>&1

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ✅ Daily Pipeline executed successfully." >> "${LOG_FILE}"
else
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ⚠️ Daily Pipeline exited with error code ${EXIT_CODE}." >> "${LOG_FILE}"
fi

exit $EXIT_CODE
