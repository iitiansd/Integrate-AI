import yaml

import streamlit as st

from clean_scenarios.remove_duplicates import process_test_scenarios
from common.utils import load_app_config
from health_check.connections_counter import increment_counter, decrement_counter

load_app_config()
from qa_agent.tc_graph import QAGraph

from pprint import pprint
import json

import asyncio

from openai import OpenAI

import pandas as pd

import io
import re
import time
import os
import uuid
import traceback
from datetime import datetime
from pytz import timezone

from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from common.utils import set_active_app

set_active_app("TestCase")


# Function to prevent screen lock
def prevent_idle_js():
    st.markdown(
        """
        <script>
        var keepAwake = setInterval(function() {
            document.dispatchEvent(new KeyboardEvent("keydown", {'key':'Shift'}));
        }, 60000); // Every 1 minute
        </script>
        """,
        unsafe_allow_html=True,
    )


#  **Call the prevent_idle_js function at the top level**
prevent_idle_js()

# st.set_page_config(layout="wide")
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
        print(
            f"app: {st.session_state.app} id: {st.session_state.session_id} logName=loginHit {id_info.get('email')} Logged in successfully : {datetime.now(timezone('Asia/Kolkata'))}")
        return id_info

    except Exception as e:
        print(
            f"logName=loginError Authentication failed: {str(e)}")
        st.error(f"Authentication failed: {str(e)}")
        st.write(f"[Retry Login with Google]({auth_url})")
        st.stop()


# Initialize session_state variables
# UI Variables
if 'scenario_doc' not in st.session_state:
    st.session_state.scenario_doc = None

if "schema_doc" not in st.session_state:
    st.session_state.schema_doc = None

if 'openapi_spec' not in st.session_state:
    st.session_state.openapi_spec = None

if 'tech_design' not in st.session_state:
    st.session_state.tech_design = None

if 'frd_document' not in st.session_state:
    st.session_state.frd_document = None

if 'other_documents' not in st.session_state:
    st.session_state.other_documents = None

if 'skip_frd' not in st.session_state:
    st.session_state.skip_frd = False

if 'skip_tech_design' not in st.session_state:
    st.session_state.skip_tech_design = False

if 'skip_schema' not in st.session_state:
    st.session_state.skip_schema = False

if 'skip_openapi_spec' not in st.session_state:
    st.session_state.skip_openapi_spec = False

if 'skip_other_documents' not in st.session_state:
    st.session_state.skip_other_documents = False

if 'test_list_data' not in st.session_state:
    st.session_state.test_list_data = []

if 'tc_tech_stack' not in st.session_state:
    st.session_state.tc_tech_stack = 'Back End'

if 'tc_figma_document' not in st.session_state:
    st.session_state.tc_figma_document = None

if 'tc_skip_figma' not in st.session_state:
    st.session_state.tc_skip_figma = False

# Graph state

if 'session_id' not in st.session_state:
    st.session_state['session_id'] = str(uuid.uuid4())

if 'tc_graph_with_memory' not in st.session_state:
    checkpoint_path = str(st.session_state['session_id']) + "_tc.sqlite"
    lc_graph_with_memory = QAGraph(checkpoint_path)  # .get_sqlite_graph()
    st.session_state['tc_graph_with_memory'] = lc_graph_with_memory

if 'invoke_graph_button_clicked' not in st.session_state:
    st.session_state['invoke_graph_button_clicked'] = False
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

# Define two columns
left_inputs, right_outputs = st.columns([0.5, 0.5])  # Adjust the ratio as needed to allocate space


def tech_stack_inputs():
    # Add a selection for "Front End" or "Back End"
    tc_tech_stack = st.radio(
        "Choose between Back End and Front End:",
        ('Back End', 'Front End'),
        key='tc_tech_stack',
        horizontal=True,

    )


def scnario_inputs():
    # Upload Scenario Document
    if st.session_state.scenario_doc is None:
        st.write('### Upload Scenario Document')
        scenario_doc = st.file_uploader('Upload Scenario Document', key='scenario_doc_uploader')
        if scenario_doc is not None:
            # Store file details in session_state
            st.session_state.scenario_doc = scenario_doc
            st.rerun()

    elif st.session_state.scenario_doc is not None:
        st.write('### Scenario Document Uploaded')
        st.write(f"**File Name:** {st.session_state.scenario_doc.name}")
        if st.button('Replace Scenario Document'):
            st.session_state.scenario_doc = None
            st.rerun()


def schema_inputs():
    # Upload Schema Document
    if st.session_state.schema_doc is None:
        st.write('### Upload Schema Document')
        schema_doc = st.file_uploader('Upload Schema Document', key='schema_doc_uploader')
        col1, col2 = st.columns(2)
        with col1:
            if schema_doc is not None:
                # Store file details in session_state
                st.session_state.schema_doc = schema_doc
                st.rerun()
        with col2:
            if st.button('Skip Schema Document'):
                st.session_state.schema_doc = None
                st.rerun()
    elif st.session_state.schema_doc is not None:
        st.write('### Schema Document Uploaded')
        st.write(f"**File Name:** {st.session_state.schema_doc.name}")
        if st.button('Replace Schema Document'):
            st.session_state.schema_doc = None
            st.rerun()
    elif st.session_state.skip_schema:
        st.write('### Schema Document Skipped')
        if st.button('Upload Schema Document'):
            st.session_state.skip_schema = False
            st.rerun()


def openapi_spec_inputs():
    # Upload OpenAPI Specification
    if st.session_state.get("openapi_spec") is None:
        st.write('### Upload OpenAPI Specification')
        openapi_spec = st.file_uploader('Upload OpenAPI Spec (YAML or JSON)', key='openapi_spec_uploader')
        col1, col2 = st.columns(2)
        with col1:
            if openapi_spec is not None:
                # Store file in session_state
                st.session_state.openapi_spec = openapi_spec
                st.rerun()
        with col2:
            if st.button('Skip OpenAPI Spec Upload'):
                st.session_state.openapi_spec = None
                st.session_state.skip_openapi_spec = True
                st.rerun()
    elif st.session_state.get("openapi_spec") is not None:
        st.write('### OpenAPI Spec Uploaded')
        st.write(f"**File Name:** {st.session_state.openapi_spec.name}")
        if st.button('Replace OpenAPI Spec'):
            st.session_state.openapi_spec = None
            st.rerun()
    elif st.session_state.get("skip_openapi_spec"):
        st.write('### OpenAPI Spec Skipped')
        if st.button('Upload OpenAPI Specification'):
            st.session_state.skip_openapi_spec = False
            st.rerun()


def figma_inputs():
    # Upload Figma Document
    if st.session_state.tc_figma_document is None and not st.session_state.tc_skip_figma:
        st.write('### Upload Figma Document (Optional)')
        tc_figma_document = st.file_uploader('Upload Figma Document', key='tc_figma_document_uploader')
        col1, col2 = st.columns(2)
        with col1:
            if tc_figma_document is not None:
                # Store file details in session_state
                st.session_state.tc_figma_document = tc_figma_document
                st.rerun()
        with col2:
            if st.button('Skip Figma Document'):
                st.session_state.tc_skip_figma = True
                st.rerun()
    elif st.session_state.tc_figma_document is not None:
        st.write('### Figma Document Uploaded')
        st.write(f"**File Name:** {st.session_state.tc_figma_document.name}")
        if st.button('Replace Figma Document'):
            st.session_state.tc_figma_document = None
            st.rerun()
    elif st.session_state.tc_skip_figma:
        st.write('### Figma Document Skipped')
        if st.button('Upload Figma Document'):
            st.session_state.tc_skip_figma = False
            st.rerun()


def frd_inputs():
    # Upload or Skip FRD Document
    if st.session_state.frd_document is None and not st.session_state.skip_frd:
        st.write('### Upload FRD Document (Optional)')
        frd_document = st.file_uploader('Upload FRD Document', key='frd_document_uploader')
        col1, col2 = st.columns(2)
        with col1:
            if frd_document is not None:
                # Store file details in session_state
                st.session_state.frd_document = frd_document
                st.rerun()
        with col2:
            if st.button('Skip FRD Document'):
                st.session_state.skip_frd = True
                st.rerun()
    elif st.session_state.frd_document is not None:
        st.write('### FRD Document Uploaded')
        st.write(f"**File Name:** {st.session_state.frd_document.name}")
        if st.button('Replace FRD Document'):
            st.session_state.frd_document = None
            st.rerun()
    elif st.session_state.skip_frd:
        st.write('### FRD Document Skipped')
        if st.button('Upload FRD Document'):
            st.session_state.skip_frd = False
            st.rerun()


def td_inputs():
    # Upload Tech Design
    # if st.session_state.tech_design is not None and not st.session_state.skip_frd and st.session_state.frd_document is None:
    if st.session_state.tech_design is None and not st.session_state.skip_tech_design:
        st.write('### Upload Tech Design Document')
        tech_design = st.file_uploader('Upload Tech Design', key='tech_design_uploader')
        col1, col2 = st.columns(2)
        with col1:
            if tech_design is not None:
                # Store file details in session_state
                st.session_state.tech_design = tech_design
                st.rerun()
        with col2:
            if st.button('Skip Tech Design'):
                st.session_state.skip_tech_design = True
                st.rerun()
    elif st.session_state.tech_design is not None:
        st.write('### Tech Design Document Uploaded')
        st.write(f"**File Name:** {st.session_state.tech_design.name}")
        if st.button('Replace Tech Design'):
            st.session_state.tech_design = None
            st.rerun()
    elif st.session_state.skip_tech_design:
        st.write('### Tech Design Document Skipped')
        if st.button('Upload Tech Design'):
            st.session_state.skip_tech_design = False
            st.rerun()


def other_document_inputs():
    MAX_ATTACHMENTS = 3
    SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json", ".docx", ".pptx", ".epub", ".html", ".htm"}

    if st.session_state.get("other_documents") is None and not st.session_state.get("skip_other_documents", False):
        st.write('### Upload Other Documents (Max: 3 files, OpenAI-supported formats only)')
        other_docs = st.file_uploader(
            'Upload Other Documents',
            accept_multiple_files=True,
            key='other_documents_uploader',
            type=[ext.strip(".") for ext in SUPPORTED_EXTENSIONS]  # type needs no dot prefix
        )
        col1, col2 = st.columns(2)
        with col1:
            if other_docs:
                invalid_files = [f.name for f in other_docs if
                                 not any(f.name.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)]
                if invalid_files:
                    st.error(f"❌ Unsupported file(s): {', '.join(invalid_files)}")
                elif len(other_docs) > MAX_ATTACHMENTS:
                    st.error(f"⚠️ You can only upload up to {MAX_ATTACHMENTS} files.")
                else:
                    st.session_state.other_documents = other_docs
                    st.rerun()
        with col2:
            if st.button('Skip Other Document Upload'):
                st.session_state.skip_other_documents = True
                st.rerun()

    elif st.session_state.get("other_documents") is not None:
        st.write('### Other Documents Uploaded')
        for file in st.session_state.other_documents:
            st.write(f" {file.name}")
        if st.button('Replace Other Documents'):
            st.session_state.other_documents = None
            st.rerun()

    elif st.session_state.get("skip_other_documents"):
        st.write('### Other Document Upload Skipped')
        if st.button('Upload Other Documents'):
            st.session_state.skip_other_documents = False
            st.rerun()


@st.fragment()
def downloaders():
    # initialize dataframe
    df = pd.DataFrame()
    # print(
    #     f"app: {st.session_state.app} id: {st.session_state.session_id} Test List Data:  {st.session_state['test_list_data']}")

    for scenario in st.session_state['test_list_data']:
        # print(f"app: {st.session_state.app} id: {st.session_state.session_id} scenario: {scenario}")
        # for test_details in scenario[1]:
        # print(f"app: {st.session_state.app} id: {st.session_state.session_id} test_details:  {scenario[1]}")
        # Assign 'internal_class' 
        temp_df = pd.DataFrame(scenario[1])
        temp_df['scenario'] = scenario[0]

        # append tests to a DataFrame
        df = pd.concat([df, temp_df], ignore_index=True)
        # Add the 'Result' column with labels
    result_labels = ['Adopt', 'New Addition', 'Not Used(Basic)', 'Not Used(Irrelevant)', 'Not Used(Other)']
    df['Result'] = result_labels * (len(df) // len(result_labels)) + result_labels[:len(df) % len(result_labels)]

    df_unique = pd.DataFrame()
    # Remove duplicate test_scenarios
    if "unique_test_cases" in st.session_state and not st.session_state["unique_test_cases"].empty:
        df_unique = st.session_state["unique_test_cases"]
        df_unique['Result'] = result_labels * (len(df_unique) // len(result_labels)) + result_labels[
                                                                                       :len(df_unique) % len(
                                                                                           result_labels)]

    # Create a BytesIO buffer to hold the XLS data
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
        if "unique_test_cases" in st.session_state and not st.session_state["unique_test_cases"].empty:
            df_unique.to_excel(writer, index=False, sheet_name='unique_cases')
        # writer.save()

    # Prepare the buffer for download
    xls_data = output.getvalue()
    st.download_button(
        label=f'Download test cases',
        data=xls_data,  # json.dumps(test_list[1],indent=4),
        file_name=f'test_scenarios.xlsx',
        mime="application/vnd.ms-excel",
        key=f"download_scenarios"
    )


# ---------------------------------------- Stage Handling  -----------------------------------------------------
# thread_config = {"configurable": {"thread_id": 1,"recursion_limit": 10000}}
def sanitize_filename(filename):
    # Replace any character that is not alphanumeric, space, or ._- with an underscore
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


thread_config = {
    "recursion_limit": 10000,
    "configurable": {
        "thread_id": 1
    }
}


def get_required_values(data, required_keys):
    """Recursively searches for required keys in a nested dictionary and returns their values.

    Args:
        data: The dictionary to search within.
        required_keys: List of keys to search for.

    Returns:
        A dictionary of found keys and their corresponding values.
    """
    found_values = {}

    def recursive_search(d):
        """Helper function to search for keys in a nested dictionary."""
        if not isinstance(d, dict):
            return False

        for key in required_keys:
            if key in d:
                found_values[key] = d[key]
            else:
                for sub_key in d:
                    if isinstance(d[sub_key], dict):
                        recursive_search(d[sub_key])

    recursive_search(data)
    return found_values


def get_progress_data(node_state: dict, global_state: dict):
    print(
        f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} start progress report")
    stage_key = next(iter(node_state))
    label = "Processing ..."
    json_data = {}
    id, current_scenario = global_state.values.get('current_scenario')
    current_test = global_state.values.get('current_test', (0, ""))
    if current_test is None:
        test_id, test_name = 0, ""
    else:
        test_id, test_name = current_test
    scenario_list = global_state.values.get('scenario_list')
    next_scenario = next((item for item in scenario_list if item[0] == (id + 1)), None)
    next_scenario = next_scenario[1] if next_scenario else ""
    # is_finished = global_state.values.get('is_finished_stage2',False)
    # if is_finished:
    #     return "complete",json_data
    print(
        f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} inited progress report")
    if stage_key == 'assist_stage1':
        print(
            f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} assist1")
        # print(graph_state_data.keys())

        is_scenario_list_processed = node_state[stage_key].get('is_scenario_list_processed', False)
        if is_scenario_list_processed:
            label = f"Finished generating test cases ..."
        else:
            id, current_scenario = node_state[stage_key].get('current_scenario', (0, ""))
            label = f'Verifying test scnarios for "{current_scenario[0]}"...'
    elif stage_key == 'reflect_stage1':
        print(
            f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} reflect1")
        stage1_results = get_required_values(node_state, ['is_finished_stage1'])
        stage1_finished = stage1_results.get('is_finished_stage1', False)
        is_scenario_list_processed = global_state.values.get('is_scenario_list_processed')

        if is_scenario_list_processed:
            label = f"Finished generating test cases for all the scenarios, please download !!!"
        elif stage1_finished:
            label = f"Identified following test cases, now generating {next_scenario} test cases ..."
            print(
                f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} ~~~~~~~~~~~~~~~~~~~~~Stage 1 completed successfully")
            # json_data = global_state.values.get('test_list')
            # st.session_state['test_list_data'].append((current_scenario[0], json_data))

            # # Download File
            # st.download_button(     
            #     label=f'Download Test File {current_scenario[0]}',
            #     data=json.dumps(json_data,indent=4),
            #     file_name="Test1.JSON",
            #     mime="application/json",
            #     key=f"download_TC_{current_scenario[0]}" 
            # )
        else:
            print(
                f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} ~~~~~~~~~~~~~~~~~~~~~Stage 1 failed")
            json_data = {'Error': f'Failed verifying test scenarios for {current_scenario[0]}, retrying!!'}

    elif stage_key == 'assist_stage2':
        print(
            f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} assist2")
        print(
            f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} Node State:  {node_state[stage_key]}")
        is_test_list_processed = node_state[stage_key].get('is_test_list_processed', False)
        if is_test_list_processed:
            label = f"Finished generating test case details ..."
        else:
            id, test_name = node_state[stage_key].get('current_test', (0, ""))
            label = f'Verifying test case details for "{test_name}"...'
        print(
            f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} end assist2")
    elif stage_key == 'reflect_stage2':
        print(
            f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} reflect2")
        stage2_results = get_required_values(node_state, ['is_finished_stage2'])
        stage2_finished = stage2_results.get('is_finished_stage2')
        test_details_finished = global_state.values.get('is_test_list_processed')

        if test_details_finished:
            label = f"Finished generating test details ..."
            # test_details_list
            json_data = global_state.values.get('test_details_list')
            st.session_state['test_list_data'].append((current_scenario[0], json_data))
            # overwrite the test_list_data with the latest data here as we already appen in grpah state
            # st.session_state['test_list_data'] = (current_scenario[0], json_data)
            print(f"app: {st.session_state.app} id: {st.session_state.session_id} #$#$Test List Data: ", json_data)

            # Dump json_data to a disk file
            if JSON_DUMPS:
                file_name = sanitize_filename(f'{current_scenario[0]}.JSON')
                with open(file_name, "w") as f:
                    json.dump(json_data, f, indent=4)

            # Download File
            st.download_button(
                label=f"Download Test Case File {current_scenario[0]}",
                data=json.dumps(json_data, indent=4),
                file_name="Test2.JSON",
                mime="application/json",
                key=f"download_detailed_{current_scenario[0]}"
            )
        elif stage2_finished:
            label = f"Generating test case details finished for {test_name} !!"
            print(
                f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} ~~~~~~~~~~~~~~~~~~~~~Stage 2 completed successfully")
            # json_data = global_state.values.get('test_list')    
            # st.session_state['test_list_data'].append((test_name, json_data))
            # print("#$#$Test List Data: ",json_data)
            # # Download File
            # st.download_button(
            #     label=f"Download Test Case File {test_name['Title']}",
            #     data=json.dumps(json_data,indent=4),
            #     file_name="Test2.JSON",
            #     mime="application/json",
            #     key=f"download_detailed_{test_name['Title']}"
            # )
        else:
            print(
                f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} ~~~~~~~~~~~~~~~~~~~~~Stage 2 failed")
            label = f"Generating test case details failed for {test_name} !!, retrying..."
        print(
            f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} end progress report")
    return label, json_data


async def run_qa_graph(inputs):
    tc_graph = st.session_state['tc_graph_with_memory']
    print(
        f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} Running stage 1 graph id ~~~~~~~~~~~~~~~~~~: ",
        tc_graph)

    async with tc_graph:
        graph_with_memory = await tc_graph.aget_sqlite_graph()
        # graph_with_memory = tc_graph.get_sqlite_graph()

        with st.status("Generating Test Cases .. ") as status:
            # update staus as per first test type
            id, current_scenario = inputs.get('current_scenario')
            status.update(label=f"Processing {current_scenario} Cases", expanded=True)
            placeholder = st.empty()

            async for output in graph_with_memory.astream(inputs, thread_config):
                global_state = await graph_with_memory.aget_state(thread_config)
                if LOG_LEVEL == "DEBUG":
                    print(
                        f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} \nMemory --- Memoey\n")
                    print("()" * 100)
                    print(
                        f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} Node State: {output}")
                    print(
                        f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} Global State: {global_state}")
                    print("()" * 100)
                # st.session_state['test_list_data'] = output
                # placeholder.json(st.session_state['test_list_data'])
                time.sleep(1)
                # Update Progress

                label, json_data = get_progress_data(output, global_state)
                # expand if we have JSON data
                do_expand = json_data != {}

                if label == "complete":
                    status.update(label="Processing Completed", expanded=do_expand, state="complete")
                else:
                    status.update(label=label, expanded=do_expand)
                placeholder.json(json_data)
    # -------------------------------------------------------------------------------------------------------------
    with st.status("Deduplicating  Test Cases .. ") as status:
        status.update(label="Removing the Duplicate Cases Started", expanded=False)
        print(
            f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} logName=postProcessHit Post-processing Started!")

        if 'test_list_data' in st.session_state and len(st.session_state['test_list_data']) != 0:
            try:
                unique_test_cases = process_test_scenarios(st.session_state['test_list_data'], app_type="case",
                                                           status=status)
                st.session_state['unique_test_cases'] = unique_test_cases
            except Exception as e:
                st.error(f"Error while removing test cases: {str(e)}")
                st.error(traceback.print_exc())
                print(
                    f"app: {st.session_state.app} id: {st.session_state.session_id}  rid: {st.session_state.request_id} logName=postProcessError error: {traceback.print_exc()}")
                st.session_state['unique_test_cases'] = pd.DataFrame()  # Assign empty dataframe on failure
        else:
            st.warning("No test cases available to process.")
            print(
                f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} logName=postProcessSuccess No test cases available to process.!")

        # Download unique test cases
        status.update(label="Finished Removing Duplicate Cases", expanded=False)


# ---------------------------------------- UI   -----------------------------------------------------
def process_button():
    # Process Button
    if (((st.session_state.tech_design or st.session_state.frd_document) and st.session_state.scenario_doc)):
        if st.button('Process'):
            increment_counter()
            placeholder = st.empty()
            placeholder.write('Processing files...')
            st.session_state['request_id'] = str(uuid.uuid4())
            print(
                f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} logName=requestHit Processing files....")

            try:
                # Create file and attachment (Uploads the user provided file to OpenAI)        
                client = OpenAI()
                file_attachments = []
                td_file = None
                frd_file = None
                schema_file = None
                openapi_spec_file = None
                figma_file = None
                scenario_list = []

                # read scenario document
                if st.session_state.scenario_doc is not None:
                    scenario_doc = st.session_state.scenario_doc
                    # Read the uploaded file
                    df = pd.read_excel(scenario_doc)

                    # Extract the columns as a list of tuples
                    # scenario_list = list(zip(df['scenarioDescription'], df['expectedResults']))
                    scenario_list = [(idx + 1, (row['scenarioDescription'], row['expectedResults']))
                                     for idx, row in df.iterrows()]

                # Add schema_file if uploaded
                if st.session_state.schema_doc is not None:
                    schema_doc = st.session_state.schema_doc
                    schema_file = client.files.create(
                        file=schema_doc, purpose="assistants"
                    )

                    file_attachments.append({
                        "file_id": schema_file.id,
                        "tools": [{"type": "file_search"}]
                    })
                # Add openapi_spec_file if uploaded
                if st.session_state.openapi_spec is not None:
                    openapi_spec_doc = st.session_state.openapi_spec
                    filename = openapi_spec_doc.name.lower()
                    if filename.endswith(".yml") or filename.endswith(".yaml"):
                        # Read YAML content and convert to JSON
                        yaml_content = yaml.safe_load(openapi_spec_doc.read())
                        json_bytes = json.dumps(yaml_content, indent=2).encode('utf-8')

                        # Create an in-memory file-like object for the JSON content
                        json_file = io.BytesIO(json_bytes)
                        json_file.name = filename.rsplit(".", 1)[0] + ".json"  # e.g., openapi.yaml → openapi.json

                        openapi_spec_file = client.files.create(file=json_file, purpose="assistants")
                    else:
                        # Upload non-YAML file directly
                        openapi_spec_file = client.files.create(file=openapi_spec_doc, purpose="assistants")

                    file_attachments.append({
                        "file_id": openapi_spec_file.id,
                        "tools": [{"type": "file_search"}]
                    })

                uploaded_file_ids = []  # To keep track of files for deletion# Add figma_file if uploaded
                if st.session_state.get("other_documents") is not None:
                    for doc in st.session_state.other_documents:
                        uploaded_file = client.files.create(
                            file=doc,
                            purpose="assistants"
                        )
                        file_attachments.append({
                            "file_id": uploaded_file.id,
                            "tools": [{"type": "file_search"}]
                        })
                        uploaded_file_ids.append(uploaded_file.id)

                # Add tech_design_file if uploaded
                if st.session_state.tech_design is not None:
                    tech_design_doc = st.session_state.tech_design
                    td_file = client.files.create(
                        file=tech_design_doc, purpose="assistants"
                    )

                    # add td and frd files to attachments if present
                    file_attachments.append(
                        {
                            "file_id": td_file.id,
                            "tools": [{"type": "file_search"}]
                        }
                    )

                # Add frd_document_file if uploaded
                if st.session_state.frd_document is not None:
                    frd_doc = st.session_state.frd_document

                    frd_file = client.files.create(
                        file=frd_doc, purpose="assistants"
                    )

                    file_attachments.append({
                        "file_id": frd_file.id,
                        "tools": [{"type": "file_search"}]
                    })

                attachment_input = {"attachments": file_attachments}
                st.session_state['uploaded_td_file'] = attachment_input

                # Prepare inputs with selected test types
                inputs = {
                    'scenario_list': scenario_list,
                    'current_scenario': scenario_list[0],
                    'tech_stack': st.session_state.tc_tech_stack,
                }

                if file_attachments:
                    inputs.update(attachment_input)
                print(
                    f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id}  \nInputs ----->:  {inputs}")
                # thread = threading.Thread(target=run_qa_graph, args=(inputs,))
                # thread.start()
                # time.sleep(5)
                placeholder.write('Generating Test cases ...')
                # run_qa_graph(inputs)
                # asyncio.run(run_qa_graph(inputs))
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:  # No event loop in this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                loop.run_until_complete(run_qa_graph(inputs))  # Run async function

                print(
                    f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} logName=successHit Process completed successfully!")
            except Exception as e:
                print(
                    f"app: {st.session_state.app} id: {st.session_state.session_id} rid: {st.session_state.request_id} logName=failureHit Error:  {e} time: {datetime.now(timezone('Asia/Kolkata'))}")
                traceback.print_exc()
                placeholder.write('Error processing files...')

            finally:
                decrement_counter()
                # cleanup files
                if schema_file:
                    client.files.delete(schema_file.id)
                if openapi_spec_file:
                    client.files.delete(openapi_spec_file.id)
                if td_file:
                    client.files.delete(td_file.id)
                if frd_file:
                    client.files.delete(frd_file.id)
                if figma_file:
                    client.files.delete(figma_file.id)
                if uploaded_file_ids:
                    for file_id in uploaded_file_ids:
                        try:
                            client.files.delete(file_id)
                        except Exception as e:
                            print(f"Error deleting file {file_id}: {e}")


# Function to create a bordered container with a given title and content
def bordered_container(title, content_function):
    with st.container(border=True):
        st.markdown(f"### {title}")
        content_function()


# place inputs in the left column
with left_inputs:
    bordered_container("Select Tech Stack", tech_stack_inputs)
    bordered_container("Upload approved Test scenarios", scnario_inputs)
    if st.session_state.tc_tech_stack == 'Back End':
        bordered_container("Upload Schema Document", schema_inputs)
        bordered_container("Upload OpenAPI Spec Document", openapi_spec_inputs)
    else:
        bordered_container("Upload Figma Document", figma_inputs)
    bordered_container("Upload FRD Document", frd_inputs)
    bordered_container("Upload Tech Design Document", td_inputs)
    bordered_container("Upload other Documents", other_document_inputs)

# place outputs and processing button in the right column
with right_outputs:
    bordered_container("Generate Test Cases:", process_button)
    bordered_container("Download Test Cases:", downloaders)