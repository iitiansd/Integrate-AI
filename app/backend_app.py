import streamlit as st

from qa_agent.graph_steps2 import QAGraph

from pprint import pprint
import json

from openai import OpenAI

import threading

import time

st.set_page_config(layout="wide")

# Initialize session_state variables
# UI Variables
if 'tech_design' not in st.session_state:
    st.session_state.tech_design = None

if 'frd_document' not in st.session_state:
    st.session_state.frd_document = None

if 'skip_frd' not in st.session_state:
    st.session_state.skip_frd = False

if 'skip_tech_design' not in st.session_state:
    st.session_state.skip_tech_design = False

if 'selected_test_types' not in st.session_state:
    st.session_state.selected_test_types = []

if 'test_type_selections' not in st.session_state:
    st.session_state.test_type_selections = {}

if 'product_focus_selection' not in st.session_state:
    st.session_state.product_focus_selection = {}

if 'selected_platform_features' not in st.session_state:
    st.session_state.selected_platform_features = []

# Deprecated
if 'test_list_data' not in st.session_state:
    st.session_state.test_list_data = []

if 'stage1_placeholder' not in st.session_state:
    st.session_state.stage1_placeholder = st.empty()

# Graph state
if 'graph_with_memory' not in st.session_state:     
    lc_graph_with_memory = QAGraph().get_memory_graph()
    st.session_state['graph_with_memory'] = lc_graph_with_memory
if 'invoke_graph_button_clicked' not in st.session_state:
    st.session_state['invoke_graph_button_clicked'] = False
if 'uploaded_td_file' not in st.session_state:
    st.session_state['uploaded_td_file'] = None

st.title('Test Case Generation')

#---------------------------------------- UI   -----------------------------------------------------

test_types = [ 
              (1, "Unit Tests"), 
              (2, "Integration Tests"), 
              (3, "API Tests"), 
              (4, "Acceptance Tests"), 
              (5, "Regression Tests"), 
              (6, "Performance Tests"), 
              (7, "Security Tests"), 
              (8, "Functional Tests"),
              (9, "Load Tests"),
              (10, "Stress Tests") ,
              (11,"end")
]

platform_features = [
            'Org Owner',
            'Org user with account level manage',
            'Org user with account level monitor',
            'Org user with tile level permission (few int manage, few int monitor)',
            'Transfer ownership',
            'Audit logs\nDo we need Audit logs task to track the customer ussage Y/N?',
            'Async Helpers',
            'Mapper 2.0 - HTTP import',
            'Mapper 2.0 - FTP import',
            'Mapper 2.0 - S3 import',
            'Mapper 2.0 - Azure Blob Storage',
            'Mapper 2.0 - Google Drive',
            'Filters (output & input)',
            'Tranform Rules',
            'AFE 2.0',
            'HTTP Export',
            'HTTP Import',
            'REST Export',
            'REST Import',
            'File Providers Export \nFTP , Amazon S3 , GDrive , Azure ',
            'File Providers Import \nFTP , Amazon S3 , GDrive , Azure ',
            'Netsuite Export\nRealtime Export',
            'Netsuite Import',
            'Salesforce Export\nRealtime Export',
            'Salesforce Import',
            'Database Export\n(Redshift, Google BigQuery, Snowflake, MSSQL, MySQL, Postgres, Mongo DB, Dynamo DB)',
            'Database Import\n(Redshift, Google BigQuery, Snowflake, MSSQL, MySQL, Postgres, Mongo DB, Dynamo DB)',
            'AS2 Export',
            'AS2 Import',
            'Blob',
            'Webhook',
            'Wrapper',
            'Pagination on Export ',
            'Flow Cloning',
            'Integration Cloning',
            'IO Stacks',
            'NS SubRecord Mapping',
            'Template Install -> Navigate to Marketplace -> Select any template -> Install the same ',
            'Template Install > using flow zip',
            'Notifications',
            'Agents\n(MS SQL/My SQL/Oracle DB/Postgre SQL/Mongo DB)',
            'Scripts, (Presend, Postsubmit, Presave,Premap, Postmap) Hooks',
            'Flow Scheduling',
            'SuiteScript_INT(V2)',
            'IO Sandbox environment',
            'Dashboared - EM2.0',
            'Line Graph',
            'AutoPilot',
            'Listener logs',
            'Integration App (IA 2.0)',
            'Marketplace',
            'Autofield mapping',
            'Flow Grouping',
            'Flow Branching - With first matching and all matching router and with combination of rules and Javascript',
            'Resource Alias',
            'ILM (Integration Lifecyce Management)',
            'Custom Settings (Integration, Flow, Export, Import, Connection)',
            'JS runtime',
            'Mapping Preview',
            'Export & Import Preview',
            'SSO',
            'MFA',
            'IO Licenses (endpoint, integrator)',
            'Flow Event Reports',
            'Amazon SP API',
            'DevOps',
            'NetSuite SS2.0 Imports (only Suite app)',
            'NetSuite SS2.0 Exports (only Suite app)',
            'Script Debugger',
            'Preview functionality where ever applicable (export, mapping, script, flow branching,etc)',
            'Mock Inputs',
            'My API',
            'Additional Search Criteria on NS lookup',
            'Show retry jobs  ',
            'IAF2.0',
            'Org Admin access ',
            'PreSavePage Hook',
            'Pre Map Hook',
            'Post Submit Hook',
            'SuiteScript Hooks (NetSuite Imports Only) - premap, post Map, post submit',
            'Flow schedule override',
            'Javascript in Input Filters',
            'Javascript in Output Filters',
            'Data URI template',
            'Override tracekey Template',
            'Batch size limit',
            'Row data - list all the supported adaptors',
            'Record Data -  list all the supported adaptors',
            'Field Level Mapping - List all the applicable adaptors',
            'List level Mappings - List all the applicable adaptors',
            'Concurrency ID lock Template',
            'Next Integration flow',
            'Connections ',
            'Tokens',
            'Subscription',
            'One to Many - list all the supported adaptors ',
            'Blob this has to be covered for all the supported adaptors',
            'Preview functionality where ever applicable (export, mapping, script, flow branching,etc) - List down all the places instead of etc',
            'Template Install - Please add ways of installing template ex: from market place, using a flow zip',
            'Cloning- please add different ways of cloning like flow cloning, integration cloning.',
            'Mapper 2.0 - List down the supported adaptors',
            'Check the sentence case format and alignmnet if any new UI form or field introduce'
]



# Define two columns
col1, col2 = st.columns([0.5, 0.5])  # Adjust the ratio as needed to allocate space

def frd_inputs():
    # Upload or Skip FRD Document
    if st.session_state.frd_document is None:
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
    if st.session_state.tech_design is None:
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

# Test Type Selection
def test_type_inputs():
    st.write('### Select Test Focus: ')
    cols = st.columns(2)  # Adjust the number of columns as needed
    test_type_options = [(id, name) for id, name in test_types if name != "end"]

    selected_test_types = []
    t_id = 1
    for index, (id, name) in enumerate(test_type_options):
        key = f"test_type_{id}"
        # Determine which column to place the checkbox in
        col = cols[index % len(cols)]
        with col:
            # Initialize and display checkbox
            st.session_state.test_type_selections[key] = st.checkbox(
                name,
                key=key,
                value=st.session_state.test_type_selections.get(key, False)
            )
            if st.session_state.test_type_selections[key]:
                selected_test_types.append((t_id, name))
                t_id = t_id + 1

    st.session_state.selected_test_types = selected_test_types

def platform_focus_inputs():
    if st.session_state.tech_design is not None:
        st.write('### Select Product Focus: ')
        # Extract the test type names from the list of tuples
        platform_feature_options = [name for  name in platform_features]
        # Display multiselect widget
        selected_platform_features = st.multiselect('Select the platform feature:', platform_feature_options)
        # Store the selected test types in session state, make list of tuple of serial number and feature name
        selected_platform_features = [(index+1, name) for index, name in enumerate(selected_platform_features)]
        st.session_state.selected_platform_features = selected_platform_features

    # Column layout
    # st.write('### Select Platform Focus: ')
    # cols = st.columns(2)  # Adjust the number of columns as needed
    # selected_platform_features = []
    # t_id = 1
    # for index, name in enumerate(platform_features):
    #     key = f"platform_feature_{index}"
    #     # Determine which column to place the checkbox in
    #     col = cols[index % len(cols)]
    #     with col:
    #         # Initialize and display checkbox
    #         st.session_state.product_focus_selection[key] = st.checkbox(
    #             name,
    #             key=key,
    #             value=st.session_state.product_focus_selection.get(key, False)
    #         )
    #         if st.session_state.product_focus_selection[key]:
    #             selected_platform_features.append((t_id, name))
    #             t_id = t_id + 1

    # st.session_state.selected_platform_features = selected_platform_features

#--------------------------------------------- UI ---------------------------------------------
def process_button():
    # Process Button
    if st.session_state.tech_design is not None and (st.session_state.frd_document is not None or st.session_state.skip_frd) and st.session_state.selected_test_types:
        if st.button('Process'):
            placeholder = st.empty()
            placeholder.write('Processing files...')
            # Access Tech Design content
            tech_design_doc = st.session_state.tech_design

            # Create file and attachment (Uploads the user provided file to OpenAI)        
            client = OpenAI()
            td_file = client.files.create(
                file=tech_design_doc, purpose="assistants"
                )

            # add td and frd files to attachments if present
            file_attachments = [
                {
                    "file_id": td_file.id,
                    "tools": [{"type": "file_search"}]
                }
            ]

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
                'test_types': st.session_state.selected_test_types,
                'current_test_type': st.session_state.selected_test_types[0],  # Use the first selected test type
                'platform_features': st.session_state.selected_platform_features,
                'current_platform_feature': st.session_state.selected_platform_features[0],  # Use the first selected platform feature 
                 
            }
            if file_attachments:
                inputs.update(attachment_input)
            print("\nInputs ----->: ",inputs)
            #thread = threading.Thread(target=run_qa_graph, args=(inputs,))
            #thread.start()
            placeholder.write('Generating Test cases ...')
            run_qa_graph(inputs)

# Create content for Stage 1
#@st.fragment(run_every="3s")
def stage1_content():
    with st.container(border=True):
        st.markdown(f"### Stage Progress...")
        placeholder = st.empty()
        #placeholder.json(st.session_state.test_list_data)
        #placeholder = st.session_state.stage1_placeholder
        if st.session_state.test_list_data:
            placeholder.json(st.session_state.test_list_data)
        else:
            placeholder.write(f'No test scenarios generated yet. {time.clock_gettime(0)}')
        

# Function to create a bordered container with a given title and content
def bordered_container(title, content_function):
    with st.container(border=True):
        st.markdown(f"### {title}")
        content_function()

@st.fragment()
def downloaders():
    for test_list in st.session_state['test_list_data']:
        print("Download Test List Data: ",test_list)
        st.download_button(
            label=f'Download {test_list[0]} Cases',
            data=json.dumps(test_list[1],indent=4),
            file_name=f'{test_list[0]}.JSON',
            mime="application/json",
            key=f"download_{test_list[0]}" 
        )


#---------------------------------------- Stage Handling  -----------------------------------------------------
thread_config = {"configurable": {"thread_id": 1}}

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

def get_progress_data(node_state:dict,global_state:dict):
    stage_key = next(iter(node_state))
    label = "Processing ..."
    json_data = {}
    id,test_type = global_state.values.get('current_test_type') 
    feature_id,feature_name = global_state.values.get('current_platform_feature',(0,""))
    test_types = global_state.values.get('test_types')    
    next_test_type = next((item for item in test_types if item[0] == (id+1)), None)
    next_test_type = next_test_type[1] if next_test_type else ""
    # is_finished = global_state.values.get('is_finished_stage2',False)
    # if is_finished:
    #     return "complete",json_data
     
    if stage_key == 'assist_stage1':
        #print(graph_state_data.keys())
        
        is_test_focus_processed = node_state[stage_key].get('is_test_list_processed',False)
        if is_test_focus_processed:
            label = f"Finished generating test focus scenarios now processing platform regression scenarios ..."
        else:
            id,test_type = node_state[stage_key].get('current_test_type',(0,""))
            label = f'Verifying test scnarios for "{test_type}"...'
    elif stage_key == 'reflect_stage1':
        stage1_results = get_required_values(node_state,['is_finished_stage1'])
        stage1_finished = stage1_results.get('is_finished_stage1',False)
        test_focus_finished = global_state.values.get('is_test_list_processed')
        
        if test_focus_finished:
            label = f"Finished generating test focus scenarios now processing platform regression scenarios ..."
        elif stage1_finished:
            label = f"Identified following scenarios, now generating {next_test_type} scenarios ..."
            print("~~~~~~~~~~~~~~~~~~~~~Stage 1 completed successfully")
            json_data = global_state.values.get('test_list')
            st.session_state['test_list_data'].append((test_type, json_data))
            
            # Download File
            st.download_button(     
                label=f'Download Test File {test_type}',
                data=json.dumps(json_data,indent=4),
                file_name="Test1.JSON",
                mime="application/json",
                key=f"download_TC_{test_type}" 
            )
        else:
            print("~~~~~~~~~~~~~~~~~~~~~Stage 1 failed")
            json_data = {'Error': f'Failed verifying test scenarios for {test_type}, retrying!!'}

    elif stage_key == 'assist_stage2':
        is_platform_focus_processed = node_state[stage_key].get('is_platform_features_processed',False)
        if is_platform_focus_processed:
            label = f"Finished generating platform regression scenarios ..."
        else:
            id,feature_name = node_state[stage_key].get('current_platform_feature',(0,""))
            label = f'Verifying platform regression scenarios for "{feature_name}"...'
    elif stage_key == 'reflect_stage2':
        stage2_results = get_required_values(node_state,['is_finished_stage2'])
        stage2_finished = stage2_results.get('is_finished_stage2')
        platform_focus_finished = global_state.values.get('is_platform_features_processed')

        if platform_focus_finished:
            label = f"Finished generating platform regression scenarios ..."
        elif stage2_finished:
            label = f"Generating regression test scenarios finished for {feature_name} !!"
            print("~~~~~~~~~~~~~~~~~~~~~Stage 2 completed successfully")
            json_data = global_state.values.get('test_list')    
            st.session_state['test_list_data'].append((feature_name, json_data))
            print("#$#$Test List Data: ",json_data)
            # Download File
            st.download_button(
                label=f"Download Test Case File {feature_name}",
                data=json.dumps(json_data,indent=4),
                file_name="Test2.JSON",
                mime="application/json",
                key=f"download_detailed_{feature_name}"
            )
        else:
            print("~~~~~~~~~~~~~~~~~~~~~Stage 2 failed")
            label = f"Generating test case details failed for {feature_name} !!, retrying..."

    return label,json_data
        

def run_qa_graph(inputs):
    graph_with_memory = st.session_state['graph_with_memory']
    print("Running stage 1 graph id ~~~~~~~~~~~~~~~~~~: ",graph_with_memory)
    
    with st.status("Generating Test Cases .. ") as status:
        #status.update(label="Processing Files.. ",expanded=True)
        # update staus as per first test type
        id,test_type = inputs.get('current_test_type')
        status.update(label=f"Processing {test_type} Cases",expanded=True)
        placeholder = st.empty()
        for output in graph_with_memory.stream(inputs, thread_config):#, interrupt_before=["assist_stage2"]):        
            print("\nMemory --- Memoey\n")
            print("()"*100)
            print("Node State: ", output)
            global_state = graph_with_memory.get_state(thread_config)
            print("Global State",global_state)
            print("()"*100)
            #st.session_state['test_list_data'] = output
            #placeholder.json(st.session_state['test_list_data'])
            time.sleep(1)
            # Update Progress
            
            label,json_data = get_progress_data(output,global_state)
            #expand if we have JSON data
            do_expand = json_data != {}
            
            if label == "complete":
                status.update(label="Processing Completed",expanded=do_expand,state="complete")
            else:
                status.update(label=label,expanded=do_expand)
            placeholder.json(json_data)

            # Downloders
            # for test_list in st.session_state['test_list_data']:
            #     st.download_button(
            #         label='Download {test_list[0]} Test Cases',
            #         data=json.dumps(test_list[1],indent=4),
            #         file_name='{test_list[0]}.JSON',
            #         mime="application/json",
            #         key=f"download_{test_list[0]}" 
            #     )
            # st.download_button(
            #stage1_content()
            #st.experimental_sleep(0.1)
    
   
#-------------------------------------------------------------------------------------------------------------
# Place the main content in the left column
with col1:
    bordered_container("FRD Details:", frd_inputs)
    bordered_container("Tech Design Details:", td_inputs)
    bordered_container("Test Types:", test_type_inputs)
    bordered_container("Platform Focus:", platform_focus_inputs)

    #stage1_content()
with col2:
    bordered_container("Generate Test Cases:", process_button)
    bordered_container("Download", downloaders)
    #bordered_container("Test Scenarios", stage1_content)


#---------------------------------------------------------------------------------------------------