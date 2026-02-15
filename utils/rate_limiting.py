"""
Rate limiting utilities for the application.
Provides a shared Limiter instance that blueprints can import and use directly.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Shared limiter instance - initialized with init_app() in create_app()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window",
    headers_enabled=True,
)
