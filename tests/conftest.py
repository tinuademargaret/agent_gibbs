import pytest
from src.database import connect, migrate, sessions, settings
from src.models import Deck
from src.qa_parser import Draft
from src.services import add_card

@pytest.fixture
def db(tmp_path):
    engine = connect(f'sqlite:///{tmp_path}/test.db')
    migrate(engine)
    factory = sessions(engine)
    with factory() as s:
        settings(s)
        deck = Deck(name='Test deck')
        s.add(deck)
        s.commit()
        add_card(s, deck.id, Draft(question='Question?', short_answer='Answer', detailed_explanation='Reason'), 'Europe/London')
        s.commit()
    yield factory
    engine.dispose()
