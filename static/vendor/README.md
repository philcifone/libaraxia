# Vendored third-party files

Served from `static/` so pages make no third-party requests and a future
Content-Security-Policy can stay `script-src 'self'`.

| File | Source | License | sha512 (base64, as in SRI) |
|---|---|---|---|
| `quagga-0.12.1.min.js` | <https://cdnjs.cloudflare.com/ajax/libs/quagga/0.12.1/quagga.min.js> (barcode scanning, `add_book.html`, `wishlist.html`) | MIT ([LICENSE-quagga.txt](LICENSE-quagga.txt)) | `bCsBoYoW6zE0aja5xcIyoCDPfT27+cGr7AOCqelttLVRGay6EKGQbR6wm6SUcUGOMGXJpj+jrIpMS6i80+kZPw==` |

The hash matched cdnjs's published SRI when vendored (2026-11-04). To check
a file: `openssl dgst -sha512 -binary FILE | base64 -w0`. To upgrade, download
the new version, compare against `https://api.cdnjs.com/libraries/<lib>/<version>?fields=sri`,
update this table and the `<script>` tags.
