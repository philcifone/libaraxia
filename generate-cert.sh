#!/bin/bash
# Generate a self-signed certificate for local HTTPS development (the camera
# for barcode scanning only works on a secure origin; see docs/HTTPS-SETUP.md).
#
#   ./generate-cert.sh                  # localhost + this machine's LAN IPs
#   ./generate-cert.sh 192.168.1.50     # add more IPs or hostnames
#
# Browsers (iOS in particular) ignore the CN and only check subjectAltName,
# so every name and IP you'll open the dev server by has to be listed there.
set -euo pipefail

mkdir -p certs

san="DNS:localhost,IP:127.0.0.1"
# IPv4 addresses on physical interfaces (skips docker/bridge/VPN ones)
for ip in $(ip -4 -o addr show scope global 2>/dev/null \
            | awk '$2 !~ /^(docker|br-|veth|wg|tun|tailscale)/ {sub(/\/.*/, "", $4); print $4}'); do
    san="$san,IP:$ip"
done
for extra in "$@"; do
    if [[ "$extra" =~ ^[0-9.]+$ ]]; then san="$san,IP:$extra"; else san="$san,DNS:$extra"; fi
done

openssl req -x509 -newkey rsa:4096 -nodes \
  -out certs/cert.pem \
  -keyout certs/key.pem \
  -days 365 \
  -subj "/CN=libaraxia-dev" \
  -addext "subjectAltName=$san"

echo "SSL certificate generated in certs/ (valid 365 days) for: $san"
echo ""
echo "To use with Flask, run:"
echo "  python3 app.py --cert certs/cert.pem --key certs/key.pem"
