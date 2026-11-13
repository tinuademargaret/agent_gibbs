from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo
from uuid import uuid4
import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from email_validator import validate_email, EmailNotValidError
from src.models import Delivery
from src.database import settings
from src.services import study_cards

class EmailError(ValueError):
    pass

def validate_settings(email, tz, local_time, enabled, confirmed):
    ZoneInfo(tz)
    time.fromisoformat(local_time)
    if email:
        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError as exc:
            raise ValueError('Enter a valid email address.') from exc
    if enabled and (not email or not confirmed):
        raise ValueError('Confirm your email address before enabling reminders.')

def eligible(value, now):
    if not value.enabled or not value.email_confirmed:
        return False
    local = now.astimezone(ZoneInfo(value.timezone))
    scheduled = datetime.combine(local.date(), time.fromisoformat(value.local_time), ZoneInfo(value.timezone))
    minutes = (local - scheduled).total_seconds() / 60
    # Daytime reminders never catch up late at night. An explicitly chosen
    # late-night time gets a narrow 30-minute window, within the same date.
    if scheduled.hour >= 22:
        return 0 <= minutes < 30
    return 0 <= minutes < 180 and local.hour < 22

def payload(config, email, count, test=False):
    if not config.app_url.startswith(('https://', 'http://localhost:')):
        raise EmailError('Set a valid APP_URL before sending email.')
    return {'from': config.email_from, 'to': [email],
            'subject': 'Flashcards: test reminder' if test else 'Your daily flashcard practice',
            'text': f'You have {count} flashcards to review today.\nReview now: {config.app_url}\n\nTo pause reminders or change their time, open Settings in the app.'}

def send(config, body, key):
    if config.test_mode:
        return 'dry_run'
    if not config.api_key or not config.email_from:
        raise EmailError('Email is not configured. Set RESEND_API_KEY and EMAIL_FROM with a verified sender.')
    try:
        response = httpx.post('https://api.resend.com/emails', json=body,
                              headers={'Authorization': f'Bearer {config.api_key}', 'Idempotency-Key': key}, timeout=20)
        if response.status_code >= 300:
            raise EmailError(f'Email provider returned HTTP {response.status_code}. Check credentials, verified sender, and provider logs.')
    except httpx.RequestError as exc:
        raise EmailError('Email provider could not be reached. The scheduled job can retry.') from exc
    return 'sent'

def send_test(s, config):
    value = settings(s)
    if not value.email or not value.email_confirmed:
        raise EmailError('Save and confirm your email address first.')
    return send(config, payload(config, value.email, len(study_cards(s, value.timezone)), test=True), f'test/{uuid4()}')

def run(factory, config, now=None, sender=send):
    now = now or datetime.now(timezone.utc)
    with factory() as s:
        value = settings(s, config.timezone, config.reminder_time)
        if not eligible(value, now):
            return 'not_due'
        local_date = now.astimezone(ZoneInfo(value.timezone)).date()
        delivery = s.scalar(select(Delivery).where(Delivery.user_id == 'owner', Delivery.local_date == local_date))
        if delivery and delivery.status == 'sent':
            return 'already_sent'
        count = len(study_cards(s, value.timezone, now=now))
        if not delivery and value.only_when_due and not count:
            return 'no_cards_due'
        body = delivery.payload if delivery else payload(config, value.email, count)
        if config.test_mode:
            return 'dry_run'  # Never consumes today's delivery slot.
        if not delivery:
            delivery = Delivery(user_id='owner', local_date=local_date, payload=body)
            s.add(delivery)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return 'claimed_elsewhere'
        # Payload is frozen before sending. Concurrent retries share the provider key.
        try:
            result = sender(config, delivery.payload, f'daily/owner/{local_date.isoformat()}')
        except EmailError as exc:
            delivery.status, delivery.error = 'failed', str(exc)
            s.commit()
            return 'failed'
        delivery.status, delivery.error = result, ''
        delivery.sent_at = now if result == 'sent' else None
        s.commit()
        return result
