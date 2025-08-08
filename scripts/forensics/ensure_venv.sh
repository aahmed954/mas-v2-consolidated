# Auto-activate the project venv if not already active
set -u
VENV="${HOME}/.venvs/masv2"
if [ -z "${VIRTUAL_ENV-}" ] || [ "${VIRTUAL_ENV}" != "${VENV}" ]; then
  if [ -f "${VENV}/bin/activate" ]; then
    echo "[INFO] Activating venv: ${VENV}"
    # shellcheck disable=SC1090
    . "${VENV}/bin/activate"
  else
    echo "[ERROR] venv not found at ${VENV}"
    exit 1
  fi
fi