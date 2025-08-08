#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/ensure_venv.sh"

MANIFEST="${1:-manifest.jsonl}"
OUTDIR="$(dirname "$MANIFEST")"
BASENAME="$(basename "$MANIFEST")"
cd "$OUTDIR"

# Compute case hash (hash of all per-file sha256 lines only)
awk -F\" '/"sha256":/ {print $4}' "$BASENAME" | sha256sum | awk '{print $1}' > "${BASENAME}.casehash"
echo "[INFO] CaseHash: $(cat ${BASENAME}.casehash)"

# Prefer SSH signature if we have an ed25519 key
if [ -f "$HOME/.ssh/id_ed25519" ]; then
  echo "[INFO] Signing with SSH key..."
  ssh-keygen -Y sign -n file -f "$HOME/.ssh/id_ed25519" "$BASENAME" >/dev/null 2>&1 || true
  mv "${BASENAME}.sig" "${BASENAME}.ssh.sig" 2>/dev/null || true
fi

# Fallback to GPG if available (detached, ASCII-armored)
if command -v gpg >/dev/null 2>&1; then
  echo "[INFO] Signing with GPG (detached)..."
  gpg --batch --yes --armor --output "${BASENAME}.gpg.asc" --detach-sign "$BASENAME" || true
fi

# Also sign the CaseHash (SSH if available)
if [ -f "$HOME/.ssh/id_ed25519" ]; then
  ssh-keygen -Y sign -n file -f "$HOME/.ssh/id_ed25519" "${BASENAME}.casehash" >/dev/null 2>&1 || true
  mv "${BASENAME}.casehash.sig" "${BASENAME}.casehash.ssh.sig" 2>/dev/null || true
fi

echo "[OK] Signatures written next to $BASENAME"