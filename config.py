import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-dev-secret-key')
    DEBUG = False
    TESTING = False
    DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///library.db')
    UPLOAD_FOLDER = os.path.join('static', 'uploads')  # Default path
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB max upload size

    # Rate Limiting Configuration
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'memory://')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True

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
    DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///library.db')
    # Development uploads folder remains relative
    UPLOAD_FOLDER = os.path.join('static', 'uploads')

class ProductionConfig(Config):
    DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:////home/phil/library-catalog/library-prod.db')
    # Production uploads folder should be absolute
    UPLOAD_FOLDER = '/home/phil/library-catalog/static/uploads'  # Adjust this path

class TestingConfig(Config):
    TESTING = True
    DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///library-test.db')
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
