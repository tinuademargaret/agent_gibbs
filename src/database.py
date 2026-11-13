from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command
from pathlib import Path
from src.models import ReminderSettings

def connect(url):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def pragmas(conn, record):
            conn.execute('PRAGMA foreign_keys=ON')
    return engine

def migrate(engine):
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')

def sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)

def settings(session, timezone='Europe/London', local_time='08:00'):
    value = session.get(ReminderSettings, 'owner')
    if value is None:
        value = ReminderSettings(user_id='owner', timezone=timezone, local_time=local_time)
        session.add(value)
        session.commit()
    return value
