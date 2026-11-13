import time
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

def verify(password, encoded):
    try:
        return PasswordHasher().verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False

def protect(st, encoded):
    if not encoded:
        st.error('Set APP_PASSWORD_HASH before opening the app. See README for the setup command.')
        st.stop()
    if st.session_state.get('authenticated') == encoded:
        if st.sidebar.button('Sign out'):
            st.session_state.clear()
            st.rerun()
        return
    st.title('A little practice, every day.')
    st.caption('Sign in to your private study space.')
    with st.form('sign_in'):
        password = st.text_input('Password', type='password')
        submit = st.form_submit_button('Sign in')
    if submit:
        if time.monotonic() < st.session_state.get('retry_at', 0):
            st.error('Please wait a few seconds before trying again.')
        elif verify(password, encoded):
            st.session_state['authenticated'] = encoded
            st.rerun()
        else:
            st.session_state['retry_at'] = time.monotonic() + 3
            st.error('Incorrect password.')
    st.stop()

if __name__ == '__main__':
    from getpass import getpass
    password = getpass('Choose an app password (at least 12 characters): ')
    if len(password) < 12:
        raise SystemExit('Use at least 12 characters.')
    print(PasswordHasher().hash(password))
