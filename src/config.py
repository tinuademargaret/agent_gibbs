import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass(frozen=True)
class Config:
    database_url: str
    password_hash: str
    app_url: str
    api_key: str
    email_from: str
    test_mode: bool
    timezone: str
    reminder_time: str

    @classmethod
    def load(cls):
        load_dotenv()
        url = os.getenv('DATABASE_URL', 'sqlite:///flashcards.db')
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql+psycopg://', 1)
        elif url.startswith('postgresql://'):
            url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
        if os.getenv('APP_ENV', 'production') != 'development' and not url.startswith('postgresql'):
            raise ValueError('Production requires an external PostgreSQL DATABASE_URL.')
        return cls(url, os.getenv('APP_PASSWORD_HASH', ''), os.getenv('APP_URL', ''),
                   os.getenv('RESEND_API_KEY', ''), os.getenv('EMAIL_FROM', ''),
                   os.getenv('EMAIL_TEST_MODE', 'true').lower() == 'true',
                   os.getenv('DEFAULT_TIMEZONE', 'Europe/London'), os.getenv('DEFAULT_REMINDER_TIME', '08:00'))
