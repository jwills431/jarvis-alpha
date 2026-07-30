#!/usr/bin/env bash
#
# Generate a self-signed TLS certificate for hosting JARVIS on the private LAN.
#
# Browsers require HTTPS before they will grant microphone access to a non-
# localhost origin, so the LAN web UI must be served over TLS. This produces a
# long-lived self-signed cert whose Subject Alternative Names cover localhost,
# 127.0.0.1, and the server's LAN address/hostname, written to a gitignored
# certs/ directory. Point config.local.json at the results:
#
#   { "tls_cert": "certs/jarvis.crt", "tls_key": "certs/jarvis.key" }
#
# Because the cert is self-signed, each client trusts it once (import certs/
# jarvis.crt into the OS/browser trust store, or accept the one-time warning).
#
# Usage:
#   scripts/make_tls_cert.sh [LAN_IP_OR_HOST ...]
#
# Examples:
#   scripts/make_tls_cert.sh 192.168.1.50
#   scripts/make_tls_cert.sh 192.168.1.50 guitech-core.local
#
# With no arguments it auto-detects the primary LAN IP.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${ROOT}/certs"
CRT="${CERT_DIR}/jarvis.crt"
KEY="${CERT_DIR}/jarvis.key"
DAYS="${JARVIS_CERT_DAYS:-825}"   # 825 = the max some clients accept for a leaf

if ! command -v openssl >/dev/null 2>&1; then
  echo "error: openssl is required but was not found on PATH" >&2
  exit 1
fi

mkdir -p "${CERT_DIR}"
chmod 700 "${CERT_DIR}"

# Collect Subject Alternative Names. localhost + loopback are always included so
# the cert also works for local development; any arguments are added as extra
# DNS or IP SANs. With no arguments, auto-detect the primary LAN IPv4.
declare -a HOSTS=("$@")
if [ "${#HOSTS[@]}" -eq 0 ]; then
  detected=""
  if command -v hostname >/dev/null 2>&1; then
    detected="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  if [ -z "${detected}" ] && command -v ip >/dev/null 2>&1; then
    detected="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  fi
  if [ -n "${detected}" ]; then
    echo "Auto-detected LAN IP: ${detected}"
    HOSTS+=("${detected}")
  else
    echo "warning: could not auto-detect a LAN IP; cert will cover localhost only." >&2
    echo "         Re-run with the server's LAN IP, e.g. scripts/make_tls_cert.sh 192.168.1.50" >&2
  fi
fi

alt="DNS:localhost,IP:127.0.0.1,IP:::1"
for h in "${HOSTS[@]}"; do
  if [[ "${h}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "${h}" == *:* ]]; then
    alt+=",IP:${h}"
  else
    alt+=",DNS:${h}"
  fi
done

echo "Generating self-signed certificate"
echo "  subjectAltName = ${alt}"
echo "  validity       = ${DAYS} days"

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout "${KEY}" -out "${CRT}" -days "${DAYS}" \
  -subj "/CN=JARVIS Local" \
  -addext "subjectAltName=${alt}" \
  -addext "keyUsage=digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"

chmod 600 "${KEY}"
chmod 644 "${CRT}"

echo
echo "Wrote:"
echo "  ${KEY}  (private key — keep secret, gitignored)"
echo "  ${CRT}  (certificate — import into client trust stores)"
echo
echo "Next: set these in config.local.json"
echo '  "tls_cert": "certs/jarvis.crt",'
echo '  "tls_key":  "certs/jarvis.key"'
