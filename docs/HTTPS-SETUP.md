# The dev server and HTTPS

The barcode scanner needs the camera, and browsers only give the camera to a
secure origin (HTTPS, or `localhost`). So the dev server runs on HTTPS, with
a certificate every browser on the LAN trusts.

## One dev server

There is one, and only one (Phil, 2026-11-15: a server per branch or
worktree, each on its own database copy and password, was impossible to keep
track of):

| | |
|---|---|
| URL | `https://192.168.1.239:5000` (or `https://localhost:5000`) |
| Database | `dev/dev.db` (gitignored), made 2026-11-15 from the old preview server's database, whose covers are the ones in `static/uploads` (`library.db` is an older copy whose covers were lost on 2026-11-11) |
| Code | the main checkout, whatever branch is checked out; Flask's reloader follows edits and branch switches |
| Service | `~/.config/systemd/user/libaraxia-dev.service` |

```bash
systemctl --user restart libaraxia-dev     # after a new migration, a new cert or .env change
systemctl --user status libaraxia-dev
journalctl --user -u libaraxia-dev -f      # the log
```

It is enabled, and lingering is on for the user (`loginctl enable-linger
phil`), so it starts at boot and keeps running after logout.

It runs `manage.py --db dev/dev.db migrate --yes` before every start, so a
restart brings the database up to the checked-out code. Note that going back
to an older branch does not undo a migration: the database stays ahead.

Logins: your own accounts, plus `claude` /
`claude-dev` (an admin, friends with Phil), which Claude uses for its
screenshots so they never change your appearance settings.

To set it up again (a new machine, or the file lost), save this as
`~/.config/systemd/user/libaraxia-dev.service`, then
`systemctl --user daemon-reload && systemctl --user enable --now libaraxia-dev`:

```ini
# Libaraxia's one dev server: HTTPS on 0.0.0.0:5000, database dev/dev.db,
# the main checkout's code (Flask's reloader follows edits and branch
# switches). Migrates before each start. See docs/HTTPS-SETUP.md.
#   systemctl --user restart libaraxia-dev
#   journalctl --user -u libaraxia-dev -f
[Unit]
Description=Libaraxia dev server (https://192.168.1.239:5000, dev/dev.db)

[Service]
WorkingDirectory=/home/phil/coding/libaraxia
Environment=DATABASE_PATH=/home/phil/coding/libaraxia/dev/dev.db
Environment=PORT=5000
Environment=PYTHONUNBUFFERED=1
ExecStartPre=/home/phil/coding/libaraxia/venv/bin/python manage.py --db dev/dev.db migrate --yes
ExecStart=/home/phil/coding/libaraxia/venv/bin/python app.py --cert certs/cert.pem --key certs/key.pem
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

A worktree has its own files, which this server doesn't see. UI work happens
in the main checkout; anything that needs its own server says its port and
database, and is shut down after.

## The certificate (mkcert)

`./generate-cert.sh` writes `certs/cert.pem` and `certs/key.pem` for
`localhost` and this machine's LAN addresses. With
[mkcert](https://github.com/FiloSottile/mkcert) installed, they are signed by
mkcert's local CA, which `mkcert -install` added to the system, Firefox and
Chrome trust stores: no warnings. Without mkcert it falls back to a
self-signed certificate, which every browser warns about.

```bash
sudo pacman -S mkcert      # once
mkcert -install            # once per machine (not as root); restart the browsers
./generate-cert.sh         # again whenever the LAN address changes
systemctl --user restart libaraxia-dev
```

The certificate lasts about two years; the CA ten.

Why not plain openssl any more: `openssl req -x509` marks its certificate as
a CA (`CA:TRUE`) by default, and Firefox refuses a CA certificate as a
site's own, with no way to click past it
(`MOZILLA_PKIX_ERROR_CA_CERT_USED_AS_END_ENTITY`). Safari accepted it, which
is why only Safari worked. The fallback in `generate-cert.sh` now sets
`CA:FALSE`.

### The iPhone

The phone has to trust mkcert's CA once:

1. Get `rootCA.pem` onto the phone. It is in `$(mkcert -CAROOT)`. Copy that
   file only; **never `rootCA-key.pem`**, which would let anyone who has it
   make certificates your devices trust.
2. Open it, then Settings → Profile Downloaded → Install.
3. Settings → General → About → Certificate Trust Settings → turn on full
   trust for "mkcert phil@gaia".

## Other ways

- **ngrok** (`ngrok http 5000`) gives a public HTTPS URL with a real
  certificate, when the phone isn't on the LAN. Needs the internet; the URL
  changes on every run.
- **Production** runs behind a reverse proxy with a real certificate; see
  `deploy/README.md`.

## Troubleshooting

- **Still a warning in Firefox**: restart it after `mkcert -install`; check
  `certs/cert.pem` is mkcert's (`openssl x509 -in certs/cert.pem -noout -issuer`).
- **No camera**: the address must be `https://`, and on the phone, the CA trusted
  (above).
- **Phone can't connect**: same Wi-Fi; port 5000 open in the firewall; the
  LAN address in the certificate (`./generate-cert.sh` again if it changed).
