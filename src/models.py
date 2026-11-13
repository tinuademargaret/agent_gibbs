from datetime import datetime, timezone, date
from sqlalchemy import String, Text, ForeignKey, DateTime, Date, UniqueConstraint, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def now():
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class Deck(Base):
    __tablename__ = 'decks'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(default='owner', index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class Card(Base):
    __tablename__ = 'cards'
    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey('decks.id'), index=True)
    question: Mapped[str] = mapped_column(Text)
    short_answer: Mapped[str] = mapped_column(Text, default='')
    detailed_explanation: Mapped[str] = mapped_column(Text, default='')
    original_imported_answer: Mapped[str] = mapped_column(Text, default='')
    original_imported_explanation: Mapped[str] = mapped_column(Text, default='')
    explanation_status: Mapped[str] = mapped_column(default='needs_explanation')
    source_name: Mapped[str] = mapped_column(default='Manual')
    source_page: Mapped[int | None]
    source_excerpt: Mapped[str] = mapped_column(Text, default='')
    tags: Mapped[str] = mapped_column(default='')
    archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class Schedule(Base):
    __tablename__ = 'card_schedule'
    card_id: Mapped[int] = mapped_column(ForeignKey('cards.id'), primary_key=True)
    due_at: Mapped[date] = mapped_column(Date, index=True)
    success_streak: Mapped[int] = mapped_column(default=0)
    interval_days: Mapped[int] = mapped_column(default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ReviewEvent(Base):
    __tablename__ = 'review_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey('cards.id'), index=True)
    token: Mapped[str] = mapped_column(unique=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    rating: Mapped[str]
    is_session_retry: Mapped[bool]

class ReminderSettings(Base):
    __tablename__ = 'reminder_settings'
    user_id: Mapped[str] = mapped_column(primary_key=True, default='owner')
    enabled: Mapped[bool] = mapped_column(default=False)
    email: Mapped[str] = mapped_column(default='')
    timezone: Mapped[str] = mapped_column(default='Europe/London')
    local_time: Mapped[str] = mapped_column(default='08:00')
    only_when_due: Mapped[bool] = mapped_column(default=True)
    email_confirmed: Mapped[bool] = mapped_column(default=False)

class Delivery(Base):
    __tablename__ = 'reminder_deliveries'
    __table_args__ = (UniqueConstraint('user_id', 'local_date'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(default='owner')
    local_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(default='pending')
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str] = mapped_column(default='')
    payload: Mapped[dict] = mapped_column(JSON)
