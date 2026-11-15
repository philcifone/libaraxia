#!/bin/bash
# Certificate for local HTTPS development (the camera for barcode scanning
# only works on a secure origin; see docs/HTTPS-SETUP.md).
#
#   ./generate-cert.sh                  # localhost + this machine's LAN IPs
#   ./generate-cert.sh 192.168.1.50     # add more IPs or hostnames
#
# With mkcert installed (and `mkcert -install` run once), the certificate is
# signed by mkcert's local CA, which Firefox, Chrome and the system already
# trust: no warnings. A phone needs that CA's root installed once
# (docs/HTTPS-SETUP.md). Without mkcert it falls back to a self-signed
# certificate, which every browser warns about.
#
# Browsers (iOS in particular) ignore the CN and only check subjectAltName,
# so every name and IP you'll open the dev server by has to be listed.
set -euo pipefail

mkdir -p certs

names=(localhost 127.0.0.1)
# IPv4 addresses on physical interfaces (skips docker/bridge/VPN ones)
for ip in $(ip -4 -o addr show scope global 2>/dev/null \
            | awk '$2 !~ /^(docker|br-|veth|wg|tun|tailscale)/ {sub(/\/.*/, "", $4); print $4}'); do
    names+=("$ip")
done
names+=("$@")

if command -v mkcert >/dev/null; then
    mkcert -cert-file certs/cert.pem -key-file certs/key.pem "${names[@]}"
    echo "Signed by mkcert's local CA ($(mkcert -CAROOT)/rootCA.pem) for: ${names[*]}"
else
    san=""
    for n in "${names[@]}"; do
        if [[ "$n" =~ ^[0-9.]+$ ]]; then san="$san,IP:$n"; else san="$san,DNS:$n"; fi
    done
    # basicConstraints CA:FALSE: openssl's default for -x509 is CA:TRUE, and
    # Firefox refuses a CA certificate as a site's own with no way past it
    # (MOZILLA_PKIX_ERROR_CA_CERT_USED_AS_END_ENTITY). Safari didn't mind.
    openssl req -x509 -newkey rsa:4096 -nodes \
      -out certs/cert.pem \
      -keyout certs/key.pem \
      -days 365 \
      -subj "/CN=libaraxia-dev" \
      -addext "subjectAltName=${san#,}" \
      -addext "basicConstraints=critical,CA:FALSE" \
      -addext "extendedKeyUsage=serverAuth"
    echo "Self-signed certificate (valid 365 days; browsers will warn) for: ${names[*]}"
fi
echo ""
echo "The dev server (libaraxia-dev, docs/HTTPS-SETUP.md) picks it up on restart:"
echo "  systemctl --user restart libaraxia-dev"
