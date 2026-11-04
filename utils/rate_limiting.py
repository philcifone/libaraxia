"""
Rate limiting utilities for the application.
Provides a shared Limiter instance that blueprints can import and use directly.

There is no global default limit. It used to be 200/day and 50/hour per IP
on every route, static files included, so a page of covers plus infinite
scroll was enough to get 429s. Limits are per route instead, where abuse
would matter: login/registration/verification, profile changes, friend and
household requests, imports (grep for @limiter.limit).

Storage is in memory, so each gunicorn worker keeps its own counts and the
effective limit is (limit x workers). That's fine for brute-force protection
at this scale (prod also sits behind Cloudflare Access). If exact limits are
ever needed, point storage_uri at Redis (e.g. "redis://localhost:6379").

Behind a reverse proxy, set TRUSTED_PROXY_COUNT so the key is the real
client IP, not the proxy's (app.py applies ProxyFix).
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Shared limiter instance - initialized with init_app() in create_app()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
    strategy="fixed-window",
    headers_enabled=True,
)
