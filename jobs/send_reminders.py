from src.config import Config
from src.database import connect, sessions
from src.reminders import run

def main():
    config = Config.load()
    try:
        result = run(sessions(connect(config.database_url)), config)
    except Exception:
        raise SystemExit('Reminder job failed. Check database connectivity, migrations, and configuration; no secrets were logged.')
    print(f'Reminder job: {result}')
    if result == 'failed':
        raise SystemExit(1)

if __name__ == '__main__':
    main()
