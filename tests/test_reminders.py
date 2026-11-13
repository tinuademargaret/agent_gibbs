from dataclasses import replace
from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from src.config import Config
from src.database import settings
from src.models import Delivery, Schedule
from src.reminders import run, EmailError, eligible, validate_settings

CONFIG = Config('', '', 'https://study.example.com', 'test-key', 'study@example.com', False, 'Europe/London', '08:00')

def at(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)

@pytest.mark.parametrize('day,utc_hour', [('2026-01-10', 8), ('2026-07-10', 7)])
def test_dst_and_saved_time_changes(db, day, utc_hour):
    with db() as s:
        pref = settings(s)
        pref.enabled = pref.email_confirmed = True
        pref.email = 'owner@example.com'
        pref.only_when_due = False
        s.commit()
    for saved, hour, minute in [('08:00', utc_hour, 0), ('10:30', utc_hour+2, 30), ('07:45', utc_hour-1, 45)]:
        with db() as s:
            settings(s).local_time = saved
            s.commit()
        with db() as s:
            pref = settings(s)
            assert pref.local_time == saved
            assert not eligible(pref, at(f'{day}T{hour:02}:{minute:02}:00').replace(minute=minute) - __import__('datetime').timedelta(minutes=1))
            assert eligible(pref, at(f'{day}T{hour:02}:{minute:02}:00'))


def test_failure_retry_frozen_payload_and_duplicate(db):
    with db() as s:
        pref = settings(s)
        pref.enabled = pref.email_confirmed = True
        pref.email = 'owner@example.com'
        pref.only_when_due = False
        s.commit()
    calls = []
    def sender(config, body, key):
        calls.append((body, key))
        if len(calls) == 1:
            raise EmailError('Temporary provider failure')
        return 'sent'
    now = at('2026-07-10T07:10:00')
    assert run(db, CONFIG, now, sender) == 'failed'
    with db() as s:
        settings(s).email = 'changed@example.com'
        s.commit()
    assert run(db, CONFIG, now, sender) == 'sent'
    assert calls[0] == calls[1]
    with db() as s:
        settings(s).local_time = '10:30'
        s.commit()
    assert run(db, CONFIG, at('2026-07-10T09:30:00'), sender) == 'already_sent'
    assert len(calls) == 2


def test_dry_run_and_catchup(db):
    with db() as s:
        pref = settings(s)
        pref.enabled = pref.email_confirmed = True
        pref.email = 'owner@example.com'
        pref.only_when_due = False
        s.commit()
    assert run(db, replace(CONFIG, test_mode=True), at('2026-01-10T08:10:00')) == 'dry_run'
    with db() as s:
        assert s.scalar(select(Delivery)) is None
    assert run(db, CONFIG, at('2026-01-10T11:00:00')) == 'not_due'
    assert run(db, CONFIG, at('2026-01-10T23:00:00')) == 'not_due'
    with pytest.raises(ValueError):
        validate_settings('bad', 'Europe/London', '08:00', True, True)
    with pytest.raises(ValueError):
        validate_settings('owner@example.com', 'Europe/London', '08:00', True, False)


def test_explicit_night_time_does_not_allow_daytime_catchup(db):
    with db() as s:
        pref = settings(s)
        pref.enabled = pref.email_confirmed = True
        pref.local_time = '21:45'
        assert not eligible(pref, at('2026-01-10T22:05:00'))
        pref.local_time = '22:05'
        assert eligible(pref, at('2026-01-10T22:15:00'))
        assert not eligible(pref, at('2026-01-10T22:35:00'))
        pref.local_time = '23:55'
        assert not eligible(pref, at('2026-01-11T00:05:00'))
