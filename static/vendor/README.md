# Vendored third-party files

Served from `static/` so pages make no third-party requests and the
Content-Security-Policy can stay `script-src 'self'`.

| File | Source | License | sha512 (base64, as in SRI) |
|---|---|---|---|
| `quagga2-1.12.1.min.js` | `dist/quagga.min.js` from the npm package [`@ericblade/quagga2@1.12.1`](https://www.npmjs.com/package/@ericblade/quagga2/v/1.12.1), also at <https://cdn.jsdelivr.net/npm/@ericblade/quagga2@1.12.1/dist/quagga.min.js> (barcode decoding for `static/scanner.js`, on `add_item.html` (Add Book, Add Movie and the wishlist's add page)) | MIT ([LICENSE-quagga2.txt](LICENSE-quagga2.txt)) | `1he4UFO/6p7g4298+BF4xJm8m+Cjpenn2VxkzN1XYDx6v9PtNfoyYDDP5gF5FGHEjTWPHLN5lsBryVHcIFSZrg==` |

`tests/test_csp.py` checks that every `.js` file here is listed in this table
with a matching hash.

Provenance of quagga2 (2026-11-07): the npm tarball matched the registry's
`dist.integrity` (`sha512-Ar7x7LHx...`), and the file's sha256
(`rmxGkQPF1CdiWppMQRdb0VQgoUqlV56lfcFXHUI0b00=`) matched jsDelivr's file
listing. It replaced Quagga 0.12.1 (unmaintained since 2017).

To check a file: `openssl dgst -sha512 -binary FILE | base64 -w0`. To
upgrade: `npm pack @ericblade/quagga2@<version>` in an empty directory,
compare the file against the registry's integrity and jsDelivr's listing
(`https://data.jsdelivr.com/v1/packages/npm/@ericblade/quagga2@<version>?structure=flat`),
then update this table and the `<script>` tags.
