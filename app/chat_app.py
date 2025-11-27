from openai import OpenAI
import streamlit as st
import openai

from common.utils import load_app_config

load_app_config()

from qa_agent.cl_agent import OpenAIAssistantExecuters
import asyncio
import json
import os
from datetime import datetime
from pytz import timezone
import uuid

from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from common.utils import set_active_app

set_active_app("ChatApp")
LOG_LEVEL = 'DEBUG'
openai_api_key = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client
client = OpenAI(api_key=openai_api_key)

# Initialize thread_id, converse_mode, uploaded_frd_id, uploaded_td_id, and uploaded_sample_id in session state if not already present
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = None

if "converse_mode" not in st.session_state:
    st.session_state["converse_mode"] = True

if "uploaded_frd_id" not in st.session_state:
    st.session_state["uploaded_frd_id"] = None

if "uploaded_td_id" not in st.session_state:
    st.session_state["uploaded_td_id"] = None

if "uploaded_sample_id" not in st.session_state:
    st.session_state["uploaded_sample_id"] = None

current_script_dir = os.path.abspath(os.path.dirname(__file__))
CLIENT_SECRET_FILE = os.path.join(current_script_dir, "client_secret.json")
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

REDIRECT_URI = os.getenv("REDIRECT_URI")  # Match this to Google Cloud Console
JSON_DUMPS = False

LOG_LEVEL = "INFO"


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
        st.session_state['session_id'] = str(uuid.uuid4())
        print(f"app: {st.session_state.app} id: {st.session_state.session_id} logName=loginHit {id_info.get('email')} Logged in successfully : {datetime.now(timezone('Asia/Kolkata'))}")
        return id_info

    except Exception as e:
        print(f"logName=loginError Authentication failed: {str(e)}")
        st.error(f"Authentication failed: {str(e)}")
        st.write(f"[Retry Login with Google]({auth_url})")
        st.stop()

# ----------------------------- Authentication code --------------------------------
user_info = authenticate_user(st)
if user_info:
    user_email = user_info["email"]
    user_name = user_info.get("name", "User")
    st.success(f"Welcome, {user_name}!")
else:
    st.write("Please log in to access the application.")
    st.stop()

# ---------------------------------------- UI   -----------------------------------------------------



file_attachments = []

def upload_document(file, file_key):
    if st.session_state[file_key] is None:
        response = client.files.create(
            file=file, 
            purpose="assistants"
        )
        st.session_state[file_key] = response.id
    return st.session_state[file_key]

def delete_uploaded_file(file_id_key):
    if st.session_state[file_id_key] is not None:
        print(f"Deleting file with ID: {st.session_state[file_id_key]}")
        client.files.delete(st.session_state[file_id_key])
        st.session_state[file_id_key] = None

with st.sidebar:
    st.header("Assistant Selection")
    assistant_options = {
        "Microservice Assistant": "asst_h4iaXXErEoKs7JUvZSJY6CZe",
        "Git Assistant": "asst_aPla1fsTn9uZadN4196sTQsH",
        "KB Assistant": "asst_V8DhPI6pYJNS5rMptP4SSr4o", # asst_18aO3jBBPmWBa4S7ZMecQqUh
        "Git With MS Assistant": "asst_ruuYwUGEcCdPjR5Foy2UlHNS",
        "Git with MS and KB Assistant": "asst_M937J7EJIUOVs888O6XL8ds0",
        "Git with MS and KB Assistant Preview": "asst_lYJEAxz8st4RMEWC7Na5fuwM",
        "AI TC Automation Preview": "asst_wz2uneuGFkKZbBHkW6BHUxQR",
    }
    selected_assistant = st.selectbox("Choose an Assistant", list(assistant_options.keys()))
    openai_assistant_id = assistant_options[selected_assistant]
    st.session_state["assist"] = OpenAIAssistantExecuters(agent_id=openai_assistant_id)

    st.checkbox("Converse Mode", key="converse_mode")
    
    st.header("Document Upload")
    # Add FRD document uploader
    uploaded_frd = st.file_uploader("Upload an FRD document", type=["pdf", "docx", "txt"], key="frd_uploader")
    if uploaded_frd is not None and st.session_state["uploaded_frd_id"] is None:
        frd_id = upload_document(uploaded_frd, "uploaded_frd_id")
        st.session_state["uploaded_frd_id"] = frd_id

    # Add Technical Design document uploader
    uploaded_td = st.file_uploader("Upload a Technical Design document", type=["pdf", "docx", "txt"], key="td_uploader")
    if uploaded_td is not None and st.session_state["uploaded_td_id"] is None:
        td_id = upload_document(uploaded_td, "uploaded_td_id")
        st.session_state["uploaded_td_id"] = td_id

    # Add Sample Request Response document uploader
    uploaded_sample = st.file_uploader("Upload a Sample Request Response document", type=["pdf", "docx", "txt"], key="sample_uploader")
    if uploaded_sample is not None and st.session_state["uploaded_sample_id"] is None:
        sample_id = upload_document(uploaded_sample, "uploaded_sample_id")
        st.session_state["uploaded_sample_id"] = sample_id

    st.header("End Chat Session")
    # Add a button to end the chat session and delete the uploaded files
    if st.button("End Chat Session"):
        delete_uploaded_file("uploaded_frd_id")
        delete_uploaded_file("uploaded_td_id")
        delete_uploaded_file("uploaded_sample_id")

        # Clear file uploaders to prevent re-upload
        for key in ["uploaded_frd_id", "uploaded_td_id", "uploaded_sample_id"]:
            st.session_state[key] = None
        st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]
        st.session_state["thread_id"] = None
        st.session_state["assist"] = None
       
        #st.rerun()

st.subheader("✨ " + selected_assistant)


if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input():
    if not openai_api_key:
        st.info("Please add your OpenAI API key to continue.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)
    
    json_data = {'input':{'promptInput':{'query':prompt}}}
    
    if st.session_state["converse_mode"] and st.session_state["thread_id"] is not None:
        json_data['input']['threadID'] = st.session_state["thread_id"]
    
    # Add uploaded documents to attachments
    if st.session_state.uploaded_frd_id is not None:
        file_attachments.append({
            "file_id": st.session_state.uploaded_frd_id,
            "tools": [{"type": "file_search"}]
        })
    if st.session_state.uploaded_td_id is not None:
        file_attachments.append({
            "file_id": st.session_state.uploaded_td_id,
            "tools": [{"type": "file_search"}]
        })
    if st.session_state.uploaded_sample_id is not None:
        file_attachments.append({
            "file_id": st.session_state.uploaded_sample_id,
            "tools": [{"type": "file_search"}]
        })
    
    if file_attachments:
        json_data['input']['attachments'] = file_attachments
         
    assist = st.session_state["assist"]
    out = asyncio.run(assist.get_query_chain(json_data['input']))
    if LOG_LEVEL == 'DEBUG':
        print('+'*100)
        print(out)
        print('+'*100)
    
    if (out.get('agent_output') and out['agent_output'].get('thread_id')):
        st.session_state["thread_id"] = out['agent_output']['thread_id']
        print(f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.thread_id} logName=requestHit")
        if (out.get('query')):
            response = out['query']
            st.session_state.messages.append({"role": "assistant", "content": response})
        else:
            response = out['agent_output']['output']
            st.session_state.messages.append({"role": "assistant", "content": response})
        st.chat_message("assistant").write(response)
    else:   
        response = "I'm sorry, I don't have an answer to that question. Can you ask me something else?"
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.chat_message("assistant").write(response)