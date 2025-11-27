import streamlit as st

from qa_agent.tc_graph_agent import QAGraph

from pprint import pprint
import json

from openai import OpenAI

import pandas as pd
import io

import time

st.set_page_config(layout="wide")

# Initialize session_state variables
# UI Variables
if 'scenario_doc' not in st.session_state:
    st.session_state.scenario_doc = None

if "schema_doc" not in st.session_state:
    st.session_state.schema_doc = None

if 'tech_design' not in st.session_state:
    st.session_state.tech_design = None

if 'frd_document' not in st.session_state:
    st.session_state.frd_document = None

if 'skip_frd' not in st.session_state:
    st.session_state.skip_frd = False

if 'skip_tech_design' not in st.session_state:
    st.session_state.skip_tech_design = False

if 'skip_schema' not in st.session_state:
    st.session_state.skip_schema = False

if 'test_list_data' not in st.session_state:
    st.session_state.test_list_data = []

if 'progress_logs' not in st.session_state:
    st.session_state.progress_logs = []

# Graph state
if 'graph_with_memory' not in st.session_state:     
    lc_graph_with_memory = QAGraph().get_memory_graph()
    st.session_state['graph_with_memory'] = lc_graph_with_memory
if 'invoke_graph_button_clicked' not in st.session_state:
    st.session_state['invoke_graph_button_clicked'] = False

#---------------------------------------- UI   -----------------------------------------------------
st.title('Test cases Generation')

# Define two columns
left_inputs, right_outputs = st.columns([0.5, 0.5])  # Adjust the ratio as needed to allocate space

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
    #if st.session_state.tech_design is not None and not st.session_state.skip_frd and st.session_state.frd_document is None:
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

@st.fragment()
def downloaders():
    #initialize dataframe
    df = pd.DataFrame()
    print("Test List Data: ",st.session_state['test_list_data'])
    for scenario in st.session_state['test_list_data']:
        print("scenario: ",scenario)
        #for test_details in scenario[1]:
        print("test_details: ",scenario[1])                  
        # Assign 'internal_class' 
        temp_df = pd.DataFrame(scenario[1])
        temp_df['scenario'] = scenario[0]

        # append tests to a DataFrame
        df = pd.concat([df, temp_df], ignore_index=True)
        # Add the 'Result' column with labels
    result_labels = ['Adopt', 'New Addition', 'Not Used(Basic)', 'Not Used(Irrelevant)', 'Not Used(Other)']
    df['Result'] = result_labels * (len(df) // len(result_labels)) + result_labels[:len(df) % len(result_labels)]
        

    # Create a BytesIO buffer to hold the XLS data
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
        writer.save()
    
    # Prepare the buffer for download
    xls_data = output.getvalue()
    st.download_button(
        label=f'Download test scenarios',
        data=xls_data,#json.dumps(test_list[1],indent=4),
        file_name=f'test_scenarios.xlsx',
        mime="application/vnd.ms-excel",
        key=f"download_scenarios" 
    )

# query input and text area to dump the output
def query_input():
    st.write('### Query Input')
    query = st.text_area('Enter your query here:', height=200)

    if st.button('Send'):
        placeholder = st.empty()
        placeholder.write('Processing query...')    

        try:
            # Create file and attachment (Uploads the user provided file to OpenAI)        
            client = OpenAI()
            file_attachments = []
            td_file = None
            frd_file = None
            figma_file = None
            scenario_list = []

            # read scenario document
            if st.session_state.scenario_doc is not None:
                scenario_doc = st.session_state.scenario_doc
                # Read the uploaded file
                df = pd.read_excel(scenario_doc)

                # Extract the columns as a list of tuples
                #scenario_list = list(zip(df['scenarioDescription'], df['expectedResults']))                   
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
                'question': query,                         
            }
            
            if file_attachments:
                inputs.update(attachment_input)
            print("\nInputs ----->: ",inputs)
            #thread = threading.Thread(target=run_qa_graph, args=(inputs,))
            #thread.start()
            #time.sleep(5)
            placeholder.write('Generating Test cases ...')
            run_qa_graph(inputs, placeholder)
        
        except Exception as e:
            print("Error: ",e)
            placeholder.write('Error processing files...')

        finally:
            # cleanup files
            if td_file:
                client.files.delete(td_file.id)
            if frd_file:
                client.files.delete(frd_file.id)
            if figma_file:
                client.files.delete(figma_file.id)
    


#---------------------------------------- Stage Handling  -----------------------------------------------------
#thread_config = {"configurable": {"thread_id": 1,"recursion_limit": 10000}}
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

def get_progress_data(node_state:dict,global_state:dict):
    print("start progress report")
    stage_key = next(iter(node_state))
    label = "Processing ..."
    json_data = {}
    id,current_scenario = global_state.values.get('current_scenario') 
    test_id,test_name = global_state.values.get('current_test',(0,""))
    scenario_list = global_state.values.get('scenario_list')    
    next_scenario = next((item for item in scenario_list if item[0] == (id+1)), None)
    next_scenario = next_scenario[1] if next_scenario else ""
    # is_finished = global_state.values.get('is_finished_stage2',False)
    # if is_finished:
    #     return "complete",json_data
    print("inited progress report")
    if stage_key == 'assist_stage1':
        print("assist1")
        #print(graph_state_data.keys())
        
        is_scenario_list_processed = node_state[stage_key].get('is_scenario_list_processed',False)
        if is_scenario_list_processed:
            label = f"Finished generating test cases ..."
        else:
            id,current_scenario = node_state[stage_key].get('current_scenario',(0,""))
            label = f'Verifying test scnarios for "{current_scenario[0]}"...'
    elif stage_key == 'reflect_stage1':
        print("reflect1")
        stage1_results = get_required_values(node_state,['is_finished_stage1'])
        stage1_finished = stage1_results.get('is_finished_stage1',False)
        is_scenario_list_processed = global_state.values.get('is_scenario_list_processed')
        
        if is_scenario_list_processed:
            label = f"Finished generating test cases for all the scenarios, please download !!!"
        elif stage1_finished:
            label = f"Identified following test cases, now generating {next_scenario} test cases ..."
            print("~~~~~~~~~~~~~~~~~~~~~Stage 1 completed successfully")
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
            print("~~~~~~~~~~~~~~~~~~~~~Stage 1 failed")
            json_data = {'Error': f'Failed verifying test scenarios for {current_scenario[0]}, retrying!!'}

    elif stage_key == 'assist_stage2':
        print("assist2")
        print("Node State: ",node_state[stage_key])
        is_test_list_processed = node_state[stage_key].get('is_test_list_processed',False)
        if is_test_list_processed:
            label = f"Finished generating test case details ..."
        else:
            id,test_name = node_state[stage_key].get('current_test',(0,""))
            label = f'Verifying test case details for "{test_name}"...'
        print("end assist2")
    elif stage_key == 'reflect_stage2':
        print("reflect2")
        stage2_results = get_required_values(node_state,['is_finished_stage2'])
        stage2_finished = stage2_results.get('is_finished_stage2')
        test_details_finished = global_state.values.get('is_test_list_processed')

        if test_details_finished:
            label = f"Finished generating test details ..."
            #test_details_list
            json_data = global_state.values.get('test_details_list')    
            st.session_state['test_list_data'].append((current_scenario[0], json_data))
            # overwrite the test_list_data with the latest data here as we already appen in grpah state
            # st.session_state['test_list_data'] = (current_scenario[0], json_data)
            print("#$#$Test List Data: ",json_data)
            # Download File
            st.download_button(
                label=f"Download Test Case File {current_scenario[0]}",
                data=json.dumps(json_data,indent=4),
                file_name="Test2.JSON",
                mime="application/json",
                key=f"download_detailed_{current_scenario[0]}"
            )
        elif stage2_finished:
            label = f"Generating test case details finished for {test_name} !!"
            print("~~~~~~~~~~~~~~~~~~~~~Stage 2 completed successfully")
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
            print("~~~~~~~~~~~~~~~~~~~~~Stage 2 failed")
            label = f"Generating test case details failed for {test_name} !!, retrying..."
        print("end progress report")
    return label,json_data
        

def run_qa_graph(inputs,placeholder):
    graph_with_memory = st.session_state['graph_with_memory']
    print("Running stage 1 graph id ~~~~~~~~~~~~~~~~~~: ",graph_with_memory)
    
    with st.status("Generating Test Cases .. ") as status:
        #status.update(label="Processing Files.. ",expanded=True)
        # update staus as per first test type
        #id,current_scenario = inputs.get('current_scenario')
        #status.update(label=f"Processing {current_scenario} Cases",expanded=True)
        #placeholder = st.empty()
        for output in graph_with_memory.stream(inputs, thread_config):#, interrupt_before=["assist_stage2"]):        
            print("\nMemory --- Memoey\n")
            print("()"*100)
            print("Node State: ", output)
            global_state = graph_with_memory.get_state(thread_config)
            print("Global State",global_state)
            print("()"*100)
            #st.session_state['test_list_data'] = output
            #placeholder.json(st.session_state['test_list_data'])
            st.session_state.progress_logs.append(str(output))
            placeholder.write("\n".join(st.session_state.progress_logs))
            #placeholder.write(output)
           
            # Update Progress
            update_progress = False
            if(update_progress):            
                label,json_data = get_progress_data(output,global_state)
                #expand if we have JSON data
                do_expand = json_data != {}
                
                if label == "complete":
                    status.update(label="Processing Completed",expanded=do_expand,state="complete")
                else:
                    status.update(label=label,expanded=do_expand)
                placeholder.json(json_data)            
   
#-------------------------------------------------------------------------------------------------------------

#---------------------------------------- UI   -----------------------------------------------------
def process_button():
    # Process Button
    if (((st.session_state.tech_design or st.session_state.frd_document) and st.session_state.scenario_doc)):
        if st.button('Process'):
            placeholder = st.empty()
            placeholder.write('Processing files...')          
            
            try:
                # Create file and attachment (Uploads the user provided file to OpenAI)        
                client = OpenAI()
                file_attachments = []
                td_file = None
                frd_file = None
                figma_file = None
                scenario_list = []

                # read scenario document
                if st.session_state.scenario_doc is not None:
                    scenario_doc = st.session_state.scenario_doc
                    # Read the uploaded file
                    df = pd.read_excel(scenario_doc)

                    # Extract the columns as a list of tuples
                    #scenario_list = list(zip(df['scenarioDescription'], df['expectedResults']))                   
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
                    'current_scenario': scenario_list[0]                 
                }
                
                if file_attachments:
                    inputs.update(attachment_input)
                print("\nInputs ----->: ",inputs)
                #thread = threading.Thread(target=run_qa_graph, args=(inputs,))
                #thread.start()
                #time.sleep(5)
                placeholder.write('Generating Test cases ...')
                run_qa_graph(inputs)
            
            except Exception as e:
                print("Error: ",e)
                placeholder.write('Error processing files...')

            finally:
                # cleanup files
                if td_file:
                    client.files.delete(td_file.id)
                if frd_file:
                    client.files.delete(frd_file.id)
                if figma_file:
                    client.files.delete(figma_file.id)


# Function to create a bordered container with a given title and content
def bordered_container(title, content_function):
    with st.container(border=True):
        st.markdown(f"### {title}")
        content_function()

# place inputs in the left column
with left_inputs:
    bordered_container("Upload approved Test scenarios", scnario_inputs)
    bordered_container("Upload Schema Document", schema_inputs)
    bordered_container("Upload FRD Document", frd_inputs)
    bordered_container("Upload Tech Design Document", td_inputs)

# place outputs and processing button in the right column
with right_outputs:
    bordered_container("Generate Test Cases:", process_button)
    bordered_container("Download Test Cases:", downloaders)
    bordered_container("Query Input:", query_input)