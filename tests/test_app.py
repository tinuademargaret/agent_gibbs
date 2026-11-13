from pathlib import Path
from datetime import time
from argon2 import PasswordHasher
from streamlit.testing.v1 import AppTest


def app(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/ui.db')
    monkeypatch.setenv('APP_PASSWORD_HASH', PasswordHasher().hash('testing-password'))
    monkeypatch.setenv('EMAIL_TEST_MODE', 'true')
    at = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py', default_timeout=20).run()
    assert not at.exception
    assert len(at.sidebar.radio) == 0  # No data/navigation before authentication.
    at.text_input[0].input('testing-password')
    at.button[0].click().run()
    assert not at.exception
    return at


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_import_review_and_settings(tmp_path, monkeypatch):
    at = app(tmp_path, monkeypatch)
    at.sidebar.radio[0].set_value('Import').run()
    at.text_input[0].input('Biology')
    button(at, 'Create deck').click().run()
    at.text_area[0].input('Q: What is a cell?\nA: Basic unit\nExplanation: Source explanation.')
    button(at, 'Preview cards').click().run()
    assert not at.exception
    next(w for w in at.text_area if w.label == 'Detailed explanation').input('Manually edited explanation.')
    button(at, 'Save preview edits').click().run()
    assert not at.exception
    button(at, 'Confirm import').click().run()
    assert not at.exception
    at.sidebar.radio[0].set_value('Review').run()
    button(at, 'Begin session').click().run()
    assert not any('Manually edited' in m.value for m in at.markdown)
    button(at, 'Reveal answer').click().run()
    assert any('Manually edited' in m.value for m in at.markdown)
    button(at, 'I missed it').click().run()
    assert any('Manually edited' in m.value for m in at.markdown)
    assert any(b.label == 'Next card →' for b in at.button)
    button(at, 'Next card →').click().run()
    button(at, 'Reveal answer').click().run()
    button(at, 'I knew it').click().run()
    button(at, 'Next card →').click().run()
    assert not at.exception
    at.sidebar.radio[0].set_value('Settings').run()
    assert at.time_input[0].value == time(8)
    for value in [time(10, 30), time(7, 45)]:
        at.time_input[0].set_value(value)
        button(at, 'Save reminder settings').click().run()
        assert not at.exception
        assert value.strftime('%H:%M') in at.info[0].value
    assert len(at.get('download_button')) == 1


def test_card_edit_cancel_and_delete(tmp_path, monkeypatch):
    at = app(tmp_path, monkeypatch)
    at.sidebar.radio[0].set_value('My decks').run()
    next(w for w in at.text_input if w.label == 'Name').input('Test')
    button(at, 'Create deck').click().run()
    next(w for w in at.text_area if w.label == 'Question').input('Original question')
    next(w for w in at.text_area if w.label == 'Short answer').input('Original answer')
    next(w for w in at.text_area if w.label == 'Detailed explanation').input('Original explanation')
    button(at, 'Save new card').click().run()
    [w for w in at.text_area if w.label == 'Question'][-1].input('Discard this')
    button(at, 'Cancel').click().run()
    assert [w for w in at.text_area if w.label == 'Question'][-1].value == 'Original question'
    [w for w in at.text_area if w.label == 'Detailed explanation'][-1].input('Saved manual rewrite')
    button(at, 'Save card').click().run()
    assert not at.exception
    assert any(m.value == 'Saved manual rewrite' for m in at.markdown)
    next(w for w in at.checkbox if w.label.startswith('Confirm permanent')).check().run()
    button(at, 'Delete card').click().run()
    assert not at.exception
    assert not any(m.value == 'Saved manual rewrite' for m in at.markdown)
