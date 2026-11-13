"""Private, source-faithful flashcard practice."""
import json
import os
from dataclasses import asdict
from datetime import time
from zoneinfo import available_timezones
import streamlit as st
from sqlalchemy import select, func
from src.auth import protect
from src.config import Config
from src.database import connect, migrate, sessions, settings
from src.models import Deck, Card, Schedule, ReviewEvent, Delivery, ReminderSettings
from src.qa_parser import Draft, parse
from src.importers import extract, MAX_BYTES
from src.services import all_cards, study_cards, add_card, update_card, delete_card, rate, today
from src.review_session import ReviewSession
from src.reminders import validate_settings, send_test, EmailError

st.set_page_config(page_title='Fieldnotes · Flashcards', page_icon='🌱', layout='wide')
try:
    for key in ('APP_ENV', 'DATABASE_URL', 'APP_PASSWORD_HASH', 'APP_URL', 'RESEND_API_KEY', 'EMAIL_FROM', 'EMAIL_TEST_MODE', 'DEFAULT_TIMEZONE', 'DEFAULT_REMINDER_TIME'):
        if key in st.secrets:
            os.environ[key] = str(st.secrets[key])
except FileNotFoundError:
    pass
try:
    config = Config.load()
except ValueError as exc:
    st.error(str(exc))
    st.stop()
protect(st, config.password_hash)

@st.cache_resource
def database(url):
    engine = connect(url)
    migrate(engine)
    return sessions(engine)

try:
    factory = database(config.database_url)
except Exception:
    st.error('Unable to initialize the database. Check DATABASE_URL and database availability.')
    st.stop()

st.sidebar.title('🌱 Fieldnotes')
st.sidebar.caption('YOUR DAILY STUDY SPACE')
page = st.sidebar.radio('Navigation', ['Home', 'Import', 'My decks', 'Review', 'Settings'], key='navigation')
st.sidebar.divider()
st.sidebar.caption('Your words. Your understanding.\nA little stronger every day.')
if config.database_url.startswith('sqlite'):
    st.sidebar.info('Local development · SQLite\nUse external PostgreSQL for deployment.')


def go_review():
    st.session_state['navigation'] = 'Review'


def editor(card, prefix, decks, review=False):
    with st.expander('Edit card'):
        revision_key = f'edit_revision_{prefix}'
        with st.form(f'edit_{prefix}_{st.session_state.get(revision_key, 0)}'):
            q = st.text_area('Question', card.question)
            a = st.text_area('Short answer', card.short_answer)
            e = st.text_area('Detailed explanation', card.detailed_explanation, height=220)
            tags = st.text_input('Tags', card.tags)
            ids = [d.id for d in decks]
            deck = st.selectbox('Deck', ids, index=ids.index(card.deck_id), format_func=lambda x: next(d.name for d in decks if d.id == x))
            archived = st.checkbox('Archived', card.archived)
            save = st.form_submit_button('Save card')
            cancel = st.form_submit_button('Cancel')
        if save:
            try:
                update_card(card, q, a, e, tags)
                card.deck_id, card.archived = deck, archived
                s.commit()
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if cancel:
            st.session_state[revision_key] = st.session_state.get(revision_key, 0) + 1
            st.rerun()
        with st.expander('Original imported content'):
            st.text(card.original_imported_answer)
            st.text(card.original_imported_explanation)
            st.text(card.source_excerpt)
        if not review:
            confirm = st.checkbox('Confirm permanent deletion, including review history', key=f'del_confirm_{prefix}')
            if st.button('Delete card', key=f'del_{prefix}', disabled=not confirm):
                delete_card(s, card)
                s.commit()
                st.rerun()


with factory() as s:
    pref = settings(s, config.timezone, config.reminder_time)
    decks = list(s.scalars(select(Deck).where(Deck.user_id == 'owner').order_by(Deck.name)))
    if page == 'Home':
        st.caption('MAKE ROOM FOR WHAT YOU KNOW')
        st.title('A little practice, every day.')
        st.write('Bring your notes. Build understanding. Come back tomorrow.')
        cards = all_cards(s)
        due = study_cards(s, pref.timezone)
        cols = st.columns(3)
        cols[0].metric('Due today', len(due))
        cols[1].metric('Your cards', len(cards))
        cols[2].metric('Decks', len(decks))
        st.divider()
        if due:
            st.subheader('Your next small step')
            overdue = sum(s.get(Schedule, c.id).due_at < today(pref.timezone) for c in due)
            st.write(f'{len(due)} cards ready for review · {overdue} overdue')
            st.button('Start review →', type='primary', on_click=go_review)
        else:
            st.subheader('All caught up' if cards else 'Start with something you want to remember')
            st.write('Import your questions, answers, and explanations, or add a card in My decks.')
        last = s.scalar(select(func.max(ReviewEvent.reviewed_at)))
        st.caption(f'Last review: {last.isoformat() if last else "No reviews yet"}')
        for deck in decks:
            with st.container(border=True):
                st.subheader(deck.name)
                st.write(deck.description or 'A collection of things worth remembering.')
                st.caption(f'{sum(c.deck_id == deck.id for c in cards)} cards')

    elif page == 'Import':
        st.title('Turn your notes into practice.')
        st.caption('Import source-written answers and explanations. Nothing is generated or rewritten.')
        with st.expander('Create a deck', expanded=not decks):
            with st.form('new_import_deck'):
                name = st.text_input('Deck name')
                if st.form_submit_button('Create deck') and name.strip():
                    s.add(Deck(name=name.strip()))
                    s.commit()
                    st.rerun()
        if not decks:
            st.info('Create a deck to begin.')
            st.stop()
        target = st.selectbox('Import into', [d.id for d in decks], format_func=lambda x: next(d.name for d in decks if d.id == x))
        upload = st.file_uploader('PDF, TXT or Markdown · up to 20 MB', type=['pdf', 'txt', 'md'])
        pasted = st.text_area('Or paste your source', height=180, placeholder='Q: What do you want to remember?\nA: Your answer\nExplanation: Your reasoning, in your words.')
        if st.button('Preview cards', type='primary'):
            try:
                if upload:
                    text, result = extract(upload.getvalue(), upload.name)
                elif pasted.strip() and len(pasted.encode()) <= MAX_BYTES:
                    text, result = pasted, parse(pasted)
                else:
                    raise ValueError('Upload a file or paste nonempty text (up to 20 MB).')
                st.session_state['drafts'] = [asdict(c) for c in result.cards]
                st.session_state['source'] = text
                st.session_state['warnings'] = result.warnings
                st.session_state['preview_id'] = st.session_state.get('preview_id', 0) + 1
            except ValueError as exc:
                st.error(str(exc))
        if 'drafts' in st.session_state:
            for warning in st.session_state['warnings']:
                st.warning(warning)
            with st.expander('Original source · use this to repair ambiguous cards'):
                st.text(st.session_state['source'])
            st.caption('Save preview edits before adding another row. Nothing is stored in your deck until Confirm import.')
            if st.button('Add a draft row'):
                st.session_state['drafts'].append(asdict(Draft()))
            st.subheader(f'{len(st.session_state["drafts"])} draft cards')
            with st.form(f'preview_{st.session_state["preview_id"]}'):
                edited = []
                for i, data in enumerate(st.session_state['drafts']):
                    with st.container(border=True):
                        st.markdown(f'**Card {i+1}**')
                        if not data['detailed_explanation'].strip():
                            st.caption('Needs explanation · excluded from study until complete')
                        q = st.text_area('Question', data['question'], key=f'q_{st.session_state["preview_id"]}_{i}')
                        a = st.text_area('Short answer', data['short_answer'], key=f'a_{st.session_state["preview_id"]}_{i}')
                        e = st.text_area('Detailed explanation', data['detailed_explanation'], height=180, key=f'e_{st.session_state["preview_id"]}_{i}')
                        remove = st.checkbox('Remove this card', key=f'remove_{st.session_state["preview_id"]}_{i}')
                        st.caption(f'Source: {data["source_name"]} · Page: {data["source_page"] or "—"}')
                        if not remove:
                            edited.append(Draft(**{**data, 'question': q, 'short_answer': a, 'detailed_explanation': e}))
                keep = st.checkbox('Keep exact duplicates (default: skip within this deck)')
                save_preview = st.form_submit_button('Save preview edits')
                approve = st.form_submit_button('Confirm import', type='primary')
            if save_preview:
                st.session_state['drafts'] = [asdict(c) for c in edited]
                st.session_state['preview_id'] += 1
                st.rerun()
            if approve:
                try:
                    if not edited:
                        raise ValueError('Add at least one card before importing.')
                    saved = sum(add_card(s, target, c, pref.timezone, keep) is not None for c in edited)
                    s.commit()
                    st.session_state.pop('drafts')
                    st.success(f'Imported {saved} cards; skipped {len(edited)-saved} exact duplicates. Open My decks or Review.')
                except ValueError as exc:
                    s.rollback()
                    st.error(str(exc))

    elif page == 'My decks':
        st.title('Your collection')
        st.caption('Keep the wording yours. Edit anything, whenever understanding changes.')
        with st.expander('Create a deck'):
            with st.form('create_deck'):
                name = st.text_input('Name')
                desc = st.text_area('Description')
                if st.form_submit_button('Create deck') and name.strip():
                    s.add(Deck(name=name.strip(), description=desc))
                    s.commit()
                    st.rerun()
        if not decks:
            st.info('Create your first deck above.')
            st.stop()
        deck_id = st.selectbox('Deck', [d.id for d in decks], format_func=lambda x: next(d.name for d in decks if d.id == x))
        deck = s.get(Deck, deck_id)
        with st.expander('Deck settings'):
            with st.form(f'deck_{deck_id}'):
                name = st.text_input('Deck name', deck.name)
                desc = st.text_area('Description', deck.description)
                if st.form_submit_button('Save deck') and name.strip():
                    deck.name, deck.description = name.strip(), desc
                    s.commit()
                    st.rerun()
            confirmed = st.checkbox('Delete this deck and all its cards and review history')
            if st.button('Delete deck', disabled=not confirmed):
                for card in all_cards(s):
                    if card.deck_id == deck_id:
                        delete_card(s, card)
                s.flush()
                s.delete(deck)
                s.commit()
                st.rerun()
        with st.expander('Add a card'):
            with st.form(f'manual_{deck_id}', clear_on_submit=True):
                q = st.text_area('Question')
                a = st.text_area('Short answer')
                e = st.text_area('Detailed explanation')
                if st.form_submit_button('Save new card'):
                    try:
                        add_card(s, deck_id, Draft(question=q, short_answer=a, detailed_explanation=e, source_name='Manual'), pref.timezone)
                        s.commit()
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
        search = st.text_input('Search questions, answers, explanations or tags').lower()
        show_archived = st.checkbox('Show archived cards')
        for card in all_cards(s):
            if card.deck_id != deck_id or (card.archived and not show_archived) or search not in '\n'.join([card.question, card.short_answer, card.detailed_explanation, card.tags]).lower():
                continue
            with st.container(border=True):
                st.markdown(card.question)
                st.caption('Archived' if card.archived else 'Needs explanation' if card.explanation_status != 'ready' else 'Needs answer' if not card.short_answer.strip() else f'Due {s.get(Schedule, card.id).due_at}')
                st.markdown(card.short_answer)
                with st.expander('Detailed explanation'):
                    st.markdown(card.detailed_explanation)
                editor(card, str(card.id), decks)

    elif page == 'Review':
        st.title('One question at a time.')
        if 'review' not in st.session_state:
            all_mode = st.checkbox('Study all complete cards, including those not due')
            chosen = study_cards(s, pref.timezone, not all_mode)
            st.write(f'{len(chosen)} cards ready')
            if not chosen:
                st.info('All caught up. Incomplete and archived cards are excluded from review.')
            if st.button('Begin session', type='primary', disabled=not chosen):
                st.session_state['review'] = ReviewSession([(c.id, False) for c in chosen])
                st.rerun()
        else:
            session = st.session_state['review']
            if session.done:
                st.subheader('A little stronger than before.')
                st.write(f'{session.knew} known · {session.missed} missed ratings (including practice retries).')
                st.caption('Missed cards remain due tomorrow. Every review has been saved.')
                if st.button('Finish session'):
                    del st.session_state['review']
                    st.rerun()
            else:
                card_id, retry = session.queue[session.position]
                card = s.get(Card, card_id)
                st.progress(session.position / len(session.queue), text=f'Card {session.position+1} of {len(session.queue)}' + (' · Practice retry' if retry else ''))
                if not card or card.archived or card.explanation_status != 'ready' or not card.short_answer.strip():
                    st.info('This card is no longer available for study.')
                    if st.button('Skip unavailable card'):
                        session.rated = True
                        session.advance()
                        st.rerun()
                else:
                    with st.container(border=True):
                        st.caption('THINK IT THROUGH')
                        st.subheader(card.question)
                        if not session.revealed:
                            if st.button('Reveal answer', type='primary'):
                                session.revealed = True
                                st.rerun()
                        else:
                            st.divider()
                            st.caption('SHORT ANSWER')
                            st.markdown(card.short_answer)
                            st.caption('DETAILED EXPLANATION')
                            st.markdown(card.detailed_explanation)
                            if not session.rated:
                                left, right = st.columns(2)
                                knew = left.button('I knew it', use_container_width=True)
                                missed = right.button('I missed it', use_container_width=True)
                                if knew or missed:
                                    rating = 'knew' if knew else 'missed'
                                    rate(s, card.id, rating, retry, pref.timezone, session.token)
                                    session.record(rating)
                                    st.rerun()
                            else:
                                st.success('Review saved. Take a moment with the explanation, then continue.')
                                if st.button('Next card →', type='primary'):
                                    session.advance()
                                    st.rerun()
                            editor(card, f'review_{card.id}', decks, review=True)
                if st.button('End session'):
                    del st.session_state['review']
                    st.rerun()

    elif page == 'Settings':
        st.title('Make it a daily habit.')
        st.caption('Pick a time that fits your day. Change it whenever you need to.')
        st.info(f'Saved reminder: {pref.local_time} · {pref.timezone} · {"Enabled" if pref.enabled else "Paused"}')
        st.write('Delivery is approximate: the independent job checks every 15 minutes. Daytime reminders catch up for up to 3 hours, before 22:00. Explicitly selected late-night times have a 30-minute window. No second daily email after a same-day time change.')
        with st.form('reminders'):
            email = st.text_input('Email address', pref.email)
            confirmed = st.checkbox('I confirm this is my email address and I want reminders here', value=False)
            enabled = st.checkbox('Enable daily reminders', pref.enabled)
            selected_time = st.time_input('Reminder time', time.fromisoformat(pref.local_time), step=60)
            st.caption('Any minute is supported. Times from 22:00 have a 30-minute delivery window ending at midnight at the latest.')
            zones = sorted(available_timezones())
            tz = st.selectbox('Time zone', zones, index=zones.index(pref.timezone))
            only_due = st.checkbox('Only email when cards are due', pref.only_when_due)
            save = st.form_submit_button('Save reminder settings', type='primary')
        if save:
            try:
                email = email.strip()
                email_confirmed = confirmed or (email == pref.email and pref.email_confirmed)
                validate_settings(email, tz, selected_time.strftime('%H:%M'), enabled, email_confirmed)
                pref.email, pref.enabled, pref.email_confirmed = email, enabled, email_confirmed
                pref.timezone, pref.local_time, pref.only_when_due = tz, selected_time.strftime('%H:%M'), only_due
                s.commit()
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if config.test_mode:
            st.warning('Email test mode is on: no real emails are sent. Set EMAIL_TEST_MODE=false after configuring the provider.')
        if st.button('Send test email'):
            try:
                result = send_test(s, config)
                st.success('Dry run complete; no email sent.' if result == 'dry_run' else 'Email accepted by the provider. Check your inbox to verify delivery.')
            except EmailError as exc:
                st.error(str(exc))
        st.subheader('Recent reminder attempts')
        logs = list(s.scalars(select(Delivery).order_by(Delivery.local_date.desc()).limit(10)))
        if logs:
            st.dataframe([{'Date': d.local_date, 'Status': d.status, 'Error': d.error} for d in logs], hide_index=True)
        else:
            st.caption('No scheduled delivery attempts yet.')
        st.subheader('Take your data with you')
        export = {}
        for model in (Deck, Card, Schedule, ReviewEvent, ReminderSettings, Delivery):
            export[model.__tablename__] = [{c.name: getattr(row, c.name) for c in model.__table__.columns} for row in s.scalars(select(model))]
        st.download_button('Export all data (JSON)', json.dumps(export, default=str, indent=2), 'flashcards-export.json', 'application/json')
        st.caption('Exports contain your study content and email address. Keep them somewhere private.')
