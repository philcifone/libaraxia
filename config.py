import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-dev-secret-key')
    DEBUG = False
    TESTING = False
    DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///library.db')
    UPLOAD_FOLDER = os.path.join('static', 'uploads')  # Default path

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
