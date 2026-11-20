# Automatic deploys

Prod pulls its own updates. Every 5 minutes a systemd timer runs `deploy.sh`. When `main` on GitHub has a new commit and that commit's CI run (the `test` job in `.github/workflows/basic-tests.yml`) passed, the script does this:

1. Fast-forwards `/home/phil/library-catalog` to the new commit. It refuses if there are local edits or the history has diverged.
2. Runs `pip install -r requirements.txt`, but only if that file changed.
3. Runs `manage.py migrate -y`, which backs up `library.db` first when there's anything to apply.
4. Restarts `library-catalog.service` and checks that `/auth/login` answers.

If any step fails, the old code is put back and restarted. The failed commit is written to `.deploy-failed` and skipped until a newer commit arrives. Nothing needs to reach into prod and no secrets are stored anywhere: the repo is public, so the CI check is an unauthenticated GitHub API call.

So the workflow is: push to `main`, CI goes green, and prod updates within about 5 minutes. A red CI run never deploys.

## Install (once, on prod)

```bash
cd /home/phil/library-catalog
git pull                       # last manual pull: brings in deploy/
chmod +x deploy/deploy.sh

# fetch must work without a passphrase or agent; the repo is public, so use https
git remote set-url origin https://github.com/philcifone/libaraxia.git

# let the deploy (running as phil) restart gunicorn, and nothing else
echo 'phil ALL=(root) NOPASSWD: /usr/bin/systemctl restart library-catalog.service' |
    sudo tee /etc/sudoers.d/libaraxia-deploy
sudo chmod 440 /etc/sudoers.d/libaraxia-deploy
sudo visudo -cf /etc/sudoers.d/libaraxia-deploy

sudo cp deploy/libaraxia-deploy.service deploy/libaraxia-deploy.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now libaraxia-deploy.timer

# the manual pull above already moved the code to main, so the timer sees
# nothing new: apply migrations and restart this one time by hand
venv/bin/python manage.py migrate
sudo systemctl restart library-catalog
```

Check `which systemctl` on prod. If it isn't `/usr/bin/systemctl`, use that path in the sudoers line.

## Day to day

```bash
systemctl list-timers libaraxia-deploy.timer     # when it runs next
journalctl -u libaraxia-deploy -n 50             # what it did
sudo systemctl start libaraxia-deploy.service    # deploy now instead of waiting
sudo systemctl disable --now libaraxia-deploy.timer   # pause deploys
```

Settings (paths, service name, health URL) are variables at the top of `deploy.sh`. Override them with `Environment=` lines via `sudo systemctl edit libaraxia-deploy.service`.

## Prod's setup, for reference

- **Outside access is a Cloudflare tunnel** (`cloudflared` on the same machine), no reverse proxy. Every outside request reaches gunicorn from 127.0.0.1 with the visitor's address in `X-Forwarded-For`, so prod's `.env` has `TRUSTED_PROXY_COUNT=1` (checked 2026-11-20). At 0, every outside visitor would share one rate-limit bucket. LAN requests carry no such header and are counted by their own address.
- Cloudflare compresses text at its edge; on the LAN, responses are uncompressed, which costs nothing noticeable. Static files carry a year's cache headers from the app itself (`utils/static_cache.py`), which Cloudflare honours; uploads are `private`, so its edge doesn't keep them.
- The database is in WAL mode (`manage.py migrate` sets it): `library.db`, `library.db-wal` and `library.db-shm` belong together. The daily ZFS snapshot takes all three at once.

## Limits

- **Migrations aren't rolled back.** A migration that fails changes nothing, because each one runs in a transaction. One that applied stays applied, even if a later step fails and the code is rolled back. Migrations here only add things, so the old code still runs. If you do need the old data, `manage.py` left `library.db.backup-*` next to the DB, and the daily ZFS snapshot is there too.
- Migrations that are risky on prod's data (prod's schema has surprised us before) should still be rehearsed on a copy of the prod DB before merging: `sqlite3 library.db ".backup /tmp/x.db" && venv/bin/python manage.py --db /tmp/x.db migrate`. Not `cp`: the DB is in WAL mode (16.0g), so a plain copy can miss what's still in `library.db-wal`. The ZFS snapshot is fine, since it takes the `-wal` and `-shm` files in the same instant.
- CI checks syntax, that the app starts, and the test suite. It can't catch everything, which is why the script health-checks after the restart.
