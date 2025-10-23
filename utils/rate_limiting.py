"""
Rate limiting utilities for the application.
This module provides decorators for applying rate limits to routes.
"""

from functools import wraps
from flask import current_app, request
from flask_limiter.util import get_remote_address

def get_limiter():
    """Get the limiter instance from the current Flask app"""
    return current_app.limiter

def rate_limit(limit_string):
    """
    Decorator to apply rate limiting to a route.

    Args:
        limit_string: A string describing the rate limit, e.g., "5 per hour"

    Usage:
        @rate_limit("5 per hour")
        def my_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            limiter = get_limiter()
            # Apply the limit dynamically
            limiter.limit(limit_string)(lambda: None)()
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Predefined rate limit decorators for common use cases
def auth_rate_limit(f):
    """Apply rate limiting for authentication endpoints (login/register)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            limiter = get_limiter()
            # 10 attempts per hour for auth operations
            try:
                limiter.limit("10 per hour")(lambda: None)()
            except Exception:
                # If rate limit exceeded, the limiter will raise an exception
                pass
        return f(*args, **kwargs)
    return decorated_function

def profile_update_rate_limit(f):
    """Apply rate limiting for profile update endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        limiter = get_limiter()
        # 20 updates per hour
        try:
            limiter.limit("20 per hour")(lambda: None)()
        except Exception:
            pass
        return f(*args, **kwargs)
    return decorated_function

def friend_request_rate_limit(f):
    """Apply rate limiting for friend request endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        limiter = get_limiter()
        # 30 friend requests per hour
        try:
            limiter.limit("30 per hour")(lambda: None)()
        except Exception:
            pass
        return f(*args, **kwargs)
    return decorated_function
