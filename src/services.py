from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, delete, func
from src.models import Card, Deck, Schedule, ReviewEvent

def today(tz, now=None):
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz)).date()

def all_cards(s):
    return list(s.scalars(select(Card).join(Deck).where(Deck.user_id == 'owner').order_by(Card.id)))

def study_cards(s, tz, due_only=True, now=None):
    query = select(Card).join(Deck).join(Schedule).where(Deck.user_id == 'owner', Card.archived == False, Card.explanation_status == 'ready', func.length(func.trim(Card.short_answer)) > 0)
    if due_only:
        query = query.where(Schedule.due_at <= today(tz, now))
    return list(s.scalars(query.order_by(Schedule.due_at, Card.id)))

def update_card(card, question, answer, explanation, tags=''):
    if not question.strip():
        raise ValueError('A question is required.')
    card.question, card.short_answer, card.detailed_explanation, card.tags = question, answer, explanation, tags
    card.explanation_status = 'ready' if explanation.strip() else 'needs_explanation'

def add_card(s, deck_id, draft, tz, keep_duplicates=False):
    if s.get(Deck, deck_id) is None:
        raise ValueError('Choose an existing deck.')
    values = asdict(draft)
    if not draft.question.strip():
        raise ValueError('Every card needs a question.')
    existing = s.scalar(select(Card.id).where(Card.deck_id == deck_id, Card.question == draft.question, Card.short_answer == draft.short_answer, Card.detailed_explanation == draft.detailed_explanation))
    if existing and not keep_duplicates:
        return None
    card = Card(deck_id=deck_id, **values)
    update_card(card, draft.question, draft.short_answer, draft.detailed_explanation, draft.tags)
    s.add(card)
    s.flush()
    s.add(Schedule(card_id=card.id, due_at=today(tz)))
    return card

def delete_card(s, card):
    s.execute(delete(ReviewEvent).where(ReviewEvent.card_id == card.id))
    s.execute(delete(Schedule).where(Schedule.card_id == card.id))
    s.delete(card)

def rate(s, card_id, rating, retry, tz, token, now=None):
    if rating not in ('knew', 'missed'):
        raise ValueError('Invalid rating.')
    if s.scalar(select(ReviewEvent.id).where(ReviewEvent.token == token)):
        return
    now = now or datetime.now(timezone.utc)
    schedule = s.scalar(select(Schedule).where(Schedule.card_id == card_id).with_for_update())
    if retry or rating == 'missed':
        schedule.success_streak, schedule.interval_days = 0, 1
    else:
        schedule.success_streak += 1
        steps = [1, 3, 7, 14, 30]
        schedule.interval_days = steps[schedule.success_streak-1] if schedule.success_streak <= 5 else min(180, schedule.interval_days * 2)
    schedule.due_at = today(tz, now) + timedelta(days=schedule.interval_days)
    schedule.last_reviewed_at = now
    s.add(ReviewEvent(card_id=card_id, token=token, rating=rating, is_session_retry=retry, reviewed_at=now))
    s.commit()
