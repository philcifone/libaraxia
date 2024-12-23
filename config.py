import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-dev-secret-key')
    DEBUG = False
    TESTING = False
    DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///library.db')  # Default SQLite database

class DevelopmentConfig(Config):
    DEBUG = True
    DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///library-dev.db')

class ProductionConfig(Config):
    DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:////home/phil/library-catalog/library-prod.db')

class TestingConfig(Config):
    TESTING = True
    DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///library-test.db')

