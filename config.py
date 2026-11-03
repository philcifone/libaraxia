import os

# app.py loads .env before importing this module, so os.getenv() here sees
# values from .env as well as real environment variables.
#
# Not configured here (see app.py / utils): SECRET_KEY, ALLOW_REGISTRATION,
# TRUSTED_PROXY_COUNT, UPLOAD_FOLDER, the database path (DATABASE_PATH,
# utils/database.py) and rate limits (utils/rate_limiting.py).

class Config:
    DEBUG = False
    TESTING = False
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB max upload size

    # Session cookie security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False  # Overridden in production

    # Remember me cookie settings
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = False  # Overridden in production
    REMEMBER_COOKIE_DURATION = 30 * 24 * 60 * 60  # 30 days in seconds

    # Email Configuration
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))

    # Email Verification Settings
    EMAIL_VERIFICATION_REQUIRED = os.getenv('EMAIL_VERIFICATION_REQUIRED', 'False').lower() == 'true'
    EMAIL_VERIFICATION_TOKEN_MAX_AGE = 86400  # 24 hours in seconds

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    # HTTPS-only cookies in production
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

class TestingConfig(Config):
    TESTING = True
