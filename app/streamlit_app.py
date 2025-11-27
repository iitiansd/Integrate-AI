import json
import os
from datetime import datetime
from pytz import timezone


import streamlit as st

st.set_page_config(layout="wide")
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2 import id_token



from st_pages import add_page_title, get_nav_from_toml, hide_pages
from common.constants import full_page_access, hide_test_pages_list, test_page_access, hide_chat_app_pages, \
    chat_page_access, hide_restircted_pages_list

# st.set_page_config(layout="wide")
current_script_dir = os.path.abspath(os.path.dirname(__file__))
CLIENT_SECRET_FILE = os.path.join(current_script_dir, "client_secret.json")
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

REDIRECT_URI = os.getenv("REDIRECT_URI")  # Match this to Google Cloud Console


# Initialize session_state variables
# UI Variables
# st.set_page_config(layout="wide")
# Write client secret JSON from environment variable to a file
def write_client_secret():
    client_secret_json = os.getenv("GOOGLE_CLIENT_SECRET_JSON")
    if not client_secret_json:
        raise ValueError("Environment variable GOOGLE_CLIENT_SECRET_JSON is not set.")

    try:
        # Parse and validate JSON structure
        json_data = json.loads(client_secret_json)
        with open(CLIENT_SECRET_FILE, "w") as f:
            json.dump(json_data, f, indent=4)
    except json.JSONDecodeError as e:
        raise ValueError("Invalid JSON format in GOOGLE_CLIENT_SECRET_JSON.") from e


def authenticate_user(st):
    """Authenticate the user via Google OAuth."""
    # Allow insecure transport for local testing
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    # Write client secret to file dynamically
    write_client_secret()

    # Return existing user info if already authenticated
    if "user_info" in st.session_state:
        return st.session_state["user_info"]

    # Initialize Google OAuth flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    # Generate the authorization URL
    auth_url, _ = flow.authorization_url(prompt="consent")

    # Check for the "code" parameter in the query
    code = st.query_params.get("code")

    if not code:
        # If the code is not present, show the login button
        st.warning("Please log in to access the application.")
        st.write(f"[Login with Google]({auth_url})")
        st.stop()

    try:
        # Exchange the authorization code for a token
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Verify and decode the ID token
        request = Request()
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, request, audience=credentials.client_id
        )

        # Store user info and credentials in session state
        st.session_state["user_info"] = id_info
        st.session_state["credentials"] = credentials
        print(
            f"logName=loginHit {id_info.get('email')} Logged in successfully : {datetime.now(timezone('Asia/Kolkata'))}")
        return id_info

    except Exception as e:
        print(f"logName=loginError Authentication failed: {str(e)}")
        st.error(f"Authentication failed: {str(e)}")
        st.write(f"[Retry Login with Google]({auth_url})")
        st.stop()


# sections = st.sidebar.toggle("Sections", value=True, key="use_sections")

nav = get_nav_from_toml(
    ".streamlit/pages.toml"
)

st.logo("logo.png")

pg = st.navigation(nav)

add_page_title(pg)

pg.run()

user_info = authenticate_user(st)
if user_info and user_info["email"] not in full_page_access:
    # if test case user, hide chat pages    
    if user_info and user_info["email"] in test_page_access:
        hide_pages(hide_chat_app_pages)
    # if chat user, hide test pages
    elif user_info and user_info["email"] in chat_page_access:
        hide_pages(hide_test_pages_list)
    else:  # normal user just gets test scenario access
        hide_pages(hide_restircted_pages_list)