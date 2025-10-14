#!/bin/bash
# Generate self-signed SSL certificate for local development

# Create certs directory
mkdir -p certs

# Generate private key and certificate
openssl req -x509 -newkey rsa:4096 -nodes \
  -out certs/cert.pem \
  -keyout certs/key.pem \
  -days 365 \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

echo "SSL certificate generated in certs/"
echo "Files created:"
echo "  - certs/cert.pem (certificate)"
echo "  - certs/key.pem (private key)"
echo ""
echo "To use with Flask, run:"
echo "  python3 app.py --cert=certs/cert.pem --key=certs/key.pem"
