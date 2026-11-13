from src.config import Config
from src.database import connect, migrate
if __name__ == '__main__':
    migrate(connect(Config.load().database_url))
    print('Database is up to date.')
