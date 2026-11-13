from datetime import datetime, timezone, timedelta
import pytest
import pymupdf
from sqlalchemy import select, func
from src.qa_parser import parse, Draft
from src.importers import extract, MAX_BYTES
from src.models import Card, Schedule, ReviewEvent
from src.services import rate, add_card, update_card, study_cards, today
from src.review_session import ReviewSession


def test_ten_entries_and_verbatim():
    explanation = 'First line\n\n- A bullet\n  indented\n```python\nQ: not a question\n```\nEquation: x = 2'
    text = '\n\n'.join(f'Q: Question {i}?\nA: Answer {i}\nDetailed explanation: {explanation}' for i in range(10))
    result = parse(text)
    assert len(result.cards) == 10
    assert all(c.detailed_explanation == explanation for c in result.cards)

@pytest.mark.parametrize('label', ['Explanation:', '**Explanation:**', '**Explanation**:', 'Reasoning:', 'Detailed explanation:'])
def test_markdown(label):
    result = parse(f'## 1. What is PCA?\n**Answer:** Variance\n{label} Exact text\nSecond line')
    assert result.cards[0].short_answer == 'Variance'
    assert result.cards[0].detailed_explanation == 'Exact text\nSecond line'


def test_pdf_and_errors():
    with pymupdf.open() as doc:
        for i in range(2):
            page = doc.new_page()
            page.insert_text((72, 72), f'Q: Question {i}?\nA: Answer {i}\nExplanation: Reason {i}')
        _, result = extract(doc.tobytes(), 'test.pdf')
    assert len(result.cards) == 2
    assert [c.source_page for c in result.cards] == [1, 2]
    with pymupdf.open() as doc:
        doc.new_page()
        _, result = extract(doc.tobytes(), 'scan.pdf')
    assert not result.cards
    assert any('scanned' in w for w in result.warnings)
    for data, name in [(b'bad', 'bad.pdf'), (b'\xff', 'bad.txt'), (b'xx', 'bad.exe'), (b'x'*(MAX_BYTES+1), 'large.txt')]:
        with pytest.raises(ValueError):
            extract(data, name)


def test_persistence_duplicates_drafts(db):
    with db() as s:
        card = s.get(Card, 1)
        update_card(card, 'Edited?', 'Edited answer', 'Edited\nexplanation')
        s.commit()
    with db() as s:
        assert s.get(Card, 1).detailed_explanation == 'Edited\nexplanation'
        draft = Draft(question='Edited?', short_answer='Edited answer', detailed_explanation='Edited\nexplanation')
        assert add_card(s, 1, draft, 'Europe/London') is None
        assert add_card(s, 1, draft, 'Europe/London', True)
        add_card(s, 1, Draft(question='Incomplete?', short_answer='Yes'), 'Europe/London')
        s.commit()
        assert len(study_cards(s, 'Europe/London')) == 2


def test_intervals_and_retry(db):
    instant = datetime(2026, 7, 2, 23, 30, tzinfo=timezone.utc)
    with db() as s:
        for i, interval in enumerate([1, 3, 7, 14, 30, 60, 120, 180, 180]):
            rate(s, 1, 'knew', False, 'Europe/London', str(i), instant)
            assert s.get(Schedule, 1).interval_days == interval
        rate(s, 1, 'missed', False, 'Europe/London', 'miss', instant)
        rate(s, 1, 'knew', True, 'Europe/London', 'retry', instant)
        rate(s, 1, 'knew', True, 'Europe/London', 'retry', instant)
        assert s.get(Schedule, 1).due_at == today('Europe/London', instant) + timedelta(days=1)
        assert s.get(Schedule, 1).success_streak == 0
        assert s.scalar(select(func.count()).select_from(ReviewEvent)) == 11


def test_reveal_rating_next_and_one_retry():
    session = ReviewSession([(1, False)])
    with pytest.raises(ValueError):
        session.record('missed')
    session.revealed = True
    session.record('missed')
    assert session.position == 0 and session.revealed and len(session.queue) == 2
    session.advance()
    assert not session.revealed
    session.revealed = True
    session.record('missed')
    session.advance()
    assert session.done and len(session.queue) == 2
