from langchain.schema import SystemMessage, HumanMessage, BaseMessage, AIMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema.runnable import RunnableMap
from langchain_openai import ChatOpenAI
from langchain.callbacks import get_openai_callback

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from qa_agent.cl_agent import OpenAIAssistantExecuters

import requests

from langchain_core.pydantic_v1 import BaseModel, Field, ValidationError
from langchain.output_parsers.openai_tools import (
    JsonOutputToolsParser,
    PydanticToolsParser,
)

import asyncio

from typing import List, Sequence, TypedDict, Annotated, Optional, Literal, Union
import operator

from langgraph.graph import END, MessageGraph, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from .sub_tc_graph import SubQAGraph  # Import SubQAGraph from the appropriate module

from openai import OpenAI

from pprint import pprint
import os
import time

from .prompts.tc_graph_prompts import get_qa_reflection_stage1_prompt, get_qa_reflection_stage2_prompt, \
    get_qa_reflection_stage3_prompt, get_general_test_case_generation_prompt, get_backend_test_case_generation_prompt, \
    get_front_end_test_case_generation_prompt

LOG_LEVEL = "Info"

# This graph is focusing to generate Test Scenarios for individual test types and platform features.

qa_reflection_model = "gpt-4-turbo"

llm = ChatOpenAI(temperature=0.0, model_name=qa_reflection_model)


class Reflection(BaseModel):
    """Reflection and Followup"""
    Finished: bool = Field(description="Based upon your reflection decide whether task is finished or not.")
    follow_up_question: str = Field(
        description="Follow up question to LLM chat which should encorage LLM to finish the task, when you think its not finished.")
    reasonings: str = Field(description="Reasoning for your reflection and follow up question.")


qa_reflection_prompt_stage1 = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            get_qa_reflection_stage1_prompt(),

        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)

qa_reflection_prompt_stage2 = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            get_qa_reflection_stage2_prompt(),
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)

qa_reflection_prompt_stage3 = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            get_qa_reflection_stage3_prompt(),
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)

qa_reflect_stage1 = qa_reflection_prompt_stage1 | llm.bind_tools(tools=[Reflection], tool_choice="Reflection")
qa_validator_stage1 = PydanticToolsParser(tools=[Reflection])

qa_reflect_stage2 = qa_reflection_prompt_stage2 | llm.bind_tools(tools=[Reflection], tool_choice="Reflection")
qa_validator_stage2 = PydanticToolsParser(tools=[Reflection])

qa_reflect_stage3 = qa_reflection_prompt_stage3 | llm.bind_tools(tools=[Reflection], tool_choice="Reflection")
qa_validator_stage3 = PydanticToolsParser(tools=[Reflection])

converse_mode = True
stage1_thread_id = None
stage2_thread_id = None
stage3_thread_id = None
max_revisions = 3
usage_limit = 25.0

stage1_assistant_id = "asst_QCXmcIT4rhtSmHpyjBIWmLsc"
stage2_assistant_id = "asst_u8bbBW8lsqzKUtmCtl1bCWZp"

# storage for connector metadata with levels resources, endpoints and endpoint content
test_metadata = {}


# define method to add testcase content to test metadata
def add_testcase_content(test_type: str, test_case_details: list[dict]):
    test_metadata.setdefault(test_type, []).extend(test_case_details)


user_journey = "Access response header for pagination"
special_instructions = "- Please only include specific and relevant test scenarios for the given product feature."


def update_testlist(
        existing: Optional[list] = None,
        updates: Optional[Union[list, Literal["clear"]]] = None,
) -> List[str]:
    if existing is None:
        existing = []
    if updates is None:
        return existing
    if updates == "clear":
        return []
    # Concatenate the lists
    return existing + updates


# Define the state for the graph
class AutoconState(TypedDict):
    input: str
    target_app: str
    message_history: Annotated[list[BaseMessage], operator.add]
    tech_stack: str
    test_list: list[tuple[int, dict]]  # list of test cases
    is_scenario_list_processed: bool
    scenario_list: list[tuple[int, (str, str)]]  # list of scenarios
    current_scenario: tuple[int, (str, str)]  # current scenario
    current_test: tuple[int, (str)]  # current test
    current_test_details: list[dict]
    test_details_list: Annotated[List[dict], update_testlist]  # list of test details
    is_test_list_processed: bool
    attachments: dict
    stage1_thread_id: str
    stage1_revisions: int
    is_finished_stage1: bool
    stage2_thread_id: str
    stage2_revisions: int
    is_finished_stage2: bool
    stage3_thread_id: str
    stage3_revisions: int
    is_finished_stage3: bool


class UsageStatistics(TypedDict):
    completion_tokens: int
    prompt_tokens: int
    total_tokens: int
    model_cost: float
    completion_cost: float
    prompt_cost: float
    total_cost: float


class QAGraph():

    def __init__(self, checkpoint_path: str):

        self.conn = None
        self.checkpointer = None
        self.checkpointer_cm = None
        self.checkpoint_path = checkpoint_path

        # Cumulative usage statistics for Genrerator
        self.cumulative_usage = {
            'completion_tokens': 0,
            'prompt_tokens': 0,
            'total_tokens': 0,
            'model_cost': 0.0,
            'completion_cost': 0.0,
            'prompt_cost': 0.0,
            'total_cost': 0.0
        }

        # Cumulative usage statistics for reflection 
        self.cumulative_usage_reflection = {
            'completion_tokens': 0,
            'prompt_tokens': 0,
            'total_tokens': 0,
            'total_cost': 0.0
        }

    def _get_run_data(self, thread_id: str, run_id: str):
        """
        Retrieve OpenAI run data using thread_id and run_id.
        """
        client = OpenAI()
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        return run

    def _check_limits(self) -> bool:
        """
        Check if the usage limits have been exceeded.
        """
        usage = self.cumulative_usage.get('total_cost', 0.0)
        return usage > usage_limit

    def _get_model_cost(self, model_name):
        model_costs = {
            'gpt-4.1': 0.0020,
            'gpt-4o': 0.0050,
            'gpt-4-turbo-2024-04-09': 0.01,
            'gpt-4-turbo': 0.01,
            'gpt-4-turbo-preview': 0.01,
            'gpt-4-0125-preview': 0.01,
            'gpt-4-1106-preview': 0.01,
            'gpt-4-0613': 0.03,
            'gpt-4-32k-0613': 0.03,
            'gpt-3.5-turbo-0125': 0.0005,
            'gpt-3.5-turbo': 0.0005,
            'gpt-3.5-turbo-1106': 0.0010,
            'gpt-3.5-turbo-16k-0613': 0.0030,
            'gpt-3.5-turbo-0613': 0.0015,

        }
        return model_costs.get(model_name, 0.0)

    # Define method to calculate usage statistics
    def _calculate_usage(self, out) -> Optional[UsageStatistics]:
        if (out['agent_output']['thread_id'] and out['agent_output']['run_id']):

            thread_id = out['agent_output']['thread_id']
            run_id = out['agent_output']['run_id']

            run_data = self._get_run_data(thread_id, run_id)
            run_completion_tokens = run_data.usage.completion_tokens
            run_prompt_tokens = run_data.usage.prompt_tokens
            run_total_tokens = run_data.usage.total_tokens
            model_cost = self._get_model_cost(run_data.model)
            completion_cost = (run_completion_tokens / 1000) * model_cost
            prompt_cost = (run_prompt_tokens / 1000) * model_cost
            total_cost = (run_total_tokens / 1000) * model_cost

            print(
                f"Current usage: Completion tokens: {run_completion_tokens}, Prompt tokens: {run_prompt_tokens}, Total tokens: {run_total_tokens}, Model cost: {model_cost}, Completion cost: {completion_cost}, Prompt cost: {prompt_cost}, Total cost: {total_cost}")

            return UsageStatistics(
                completion_tokens=run_completion_tokens,
                prompt_tokens=run_prompt_tokens,
                total_tokens=run_total_tokens,
                model_cost=model_cost,
                completion_cost=completion_cost,
                prompt_cost=prompt_cost,
                total_cost=total_cost
            )
        else:
            raise ValueError("Missing thread_id or run_id in output data")

    # Define method to caluculate cumulative usage statistics
    def _calculate_cumulative_usage(self, out, usage) -> Optional[UsageStatistics]:
        # calculate cumulative usage statistics using calculate_usage method
        usage_stats = self._calculate_usage(out)
        if usage_stats:
            usage['completion_tokens'] += usage_stats['completion_tokens']
            usage['prompt_tokens'] += usage_stats['prompt_tokens']
            usage['total_tokens'] += usage_stats['total_tokens']
            usage['completion_cost'] += usage_stats['completion_cost']
            usage['prompt_cost'] += usage_stats['prompt_cost']
            usage['total_cost'] += usage_stats['total_cost']
            print(
                f"Cumulative Usage: Completion tokens: {usage['completion_tokens']}, Prompt tokens: {usage['prompt_tokens']}, Total tokens: {usage['total_tokens']}, Model cost: {usage['model_cost']}, Completion cost: {usage['completion_cost']}, Prompt cost: {usage['prompt_cost']}, Total cost: {usage['total_cost']}")
        return usage

    # Define method to calculate cumulative usage statistics for reflection
    def _calculate_cumulative_usage_reflection(self, cb, usage) -> Optional[UsageStatistics]:

        if cb:
            usage['completion_tokens'] += cb.completion_tokens
            usage['prompt_tokens'] += cb.prompt_tokens
            usage['total_tokens'] += cb.total_tokens
            usage['total_cost'] += cb.total_cost
            print(
                f"Cumulative Usage Reflection: Completion tokens: {usage['completion_tokens']}, Prompt tokens: {usage['prompt_tokens']}, Total tokens: {usage['total_tokens']}, Total cost: {usage['total_cost']}")
        return usage

    
    def _sim_assist_stage1_node(self, state: AutoconState):
        print("assist state:", type(state), state)
        content = 'Based on the information extracted from the documentation provided, here is the complete list of Salesforce B2B and D2C Commerce Resources formatted as requested:\n\n```json\n{\n  "resources": [\n    "Commerce Extension Mapping",\n    "Commerce Extension Mappings",\n    "Commerce Extension Provider",\n    "Commerce Extension Providers",\n    "Commerce Extensions",\n    "Commerce Import Category Job Create",\n    "Commerce Import Category Job Manage",\n    "Commerce Import Product Job Create",\n    "Commerce Import Product Job Manage",\n    "Commerce Product Import Resource",\n    "Commerce Webstore Account Addresses",\n    "Commerce Webstore Account Address",\n    "Commerce Webstore Application Context",\n    "Commerce Webstore Calculate Taxes",\n    "Commerce Webstore Carts",\n    "Commerce Webstore Cart",\n    "Commerce Webstore Cart Add to Wishlist",\n    "Commerce Webstore Cart Arrange Items",\n    "Commerce Webstore Cart Clone",\n    "Commerce Webstore Cart Make Primary",\n    "Commerce Webstore Cart Preserve",\n    "Commerce Webstore Cart Coupons",\n    "Commerce Webstore Cart Coupon",\n    "Commerce Webstore Cart Delivery Group",\n    "Commerce Webstore Cart Delivery Groups",\n    "Commerce Webstore Cart Inventory Reservations (Pilot)",\n    "Commerce Webstore Cart Messages Set Visibility",\n    "Commerce Webstore Cart Promotions",\n    "Commerce Webstore Cart Items",\n    "Commerce Webstore Cart Items Batch",\n    "Commerce Webstore Cart Item",\n    "Commerce Webstore Cart Items Promotions",\n    "Commerce Webstore Cart Product",\n    "Commerce Webstore Cart Products",\n    "Commerce Webstore Checkout",\n    "Commerce Webstore Checkout Payments",\n    "Commerce Webstore Checkout Orders",\n    "Commerce Webstore Checkouts",\n    "Commerce Webstore Externally Managed Accounts",\n    "Commerce Webstore Order Summaries",\n    "Commerce Webstore Order Summary",\n    "Commerce Webstore Order Summary Adjustments",\n    "Commerce Webstore Order Summary Lookup (Developer Preview)",\n    "Commerce Webstore Order Delivery Groups",\n    "Commerce Webstore Order Items",\n    "Commerce Webstore Order Items Adjustments",\n    "Commerce Webstore Order Summaries Add Order to Cart",\n    "Commerce Webstore Order Summaries Adjustment Aggregates",\n    "Commerce Webstore Order Shipments",\n    "Commerce Webstore Shipment Items",\n    "Commerce Webstore Payments Token"\n  ]\n}\n```\n\nThis list represents the Salesforce B2B and D2C Commerce Resources mentioned in the provided document【9†source】. Note that any URI formatting was omitted as per your request.'
        out_message = AIMessage(content=content)
        resources = [
            'Commerce Extension Mapping',
            'Commerce Extension Mappings',
            'Commerce Extension Provider',
        ]
        return {"message_history": [out_message], "resources": resources}

    def get_test_schema(self, state: AutoconState):
        tech_stack = state['tech_stack']
        if tech_stack == "Back End":
            return [
                {
                    "id": "error",
                    "Title": "error",
                    "Type": "error",
                    "Pre_Conditions": "error",
                    "Expected_Result": "error",
                    "Request_Body": "error",
                    "Response": "error",
                    "scenario": state['current_scenario'][1],
                    "Result": "error"
                }
            ]

        else:
            return [
                {
                    "id": "error",
                    "Title": "error",
                    "Type": "error",
                    "Pre_Conditions": "error",
                    "Test_Steps": "error",
                    "Expected_Result": "error",
                    "scenario": state['current_scenario'][1],
                    "Result": "error"
                }
            ]

    def _assist_stage1_node(self, state: AutoconState):
        if LOG_LEVEL == "Debug":
            print("assist stage1:", type(state), state)
            print(type(state), state)

        # TO DO check if app resources are already cached for reuse while resuming from stage 2
        # if state['resources']:
        #     print("resources already cached")
        #     return {"message_history":[HumanMessage(content="Resources already cached")],"resources": state['resources'],"stage2_revisions":0}
        global stage1_thread_id
        global user_journey

        current_scenario = state['current_scenario']
        total_scenarios = len(state['scenario_list'])

        query = ""

        out_message = None
        test_list = None

        # check if we are revising or processing new app
        # check whether we are revising or processing new resources
        stage1_revisions = state.get('stage1_revisions')
        is_revision = stage1_revisions is not None and stage1_revisions > 0
        is_finished_stage1 = state.get('is_finished_stage1')
        is_finished_stage2 = state.get('is_finished_stage2')
        # total_test_types = len(state['test_types'])
        # current_test_type = state['current_test_type']
        # is_test_list_processed = state.get('is_test_list_processed')
        is_scenario_list_processed = state.get('is_scenario_list_processed')
        # print("current_test_type",current_test_type[0],total_test_types)

        # TO DO: Differed for test case generations
        acceptance_criteria = ""

        # acceptance_criteria = f""" # Consider following acceptance criteria, while generating Test Scenarios:
        # - Verify when the user clicks on the 'Clone lookup cache' action, it will be navigated to the clone preview page.
        # - The user must be able to provide a Name, Description, and Environment(if a sandbox license is present).
        # - Verify the info text and help texts for fields.
        # - Upon clicking on the 'Clone lookup cache' button, the new lookup cache should be created and the user should be navigated to lookup caches list.
        # - If the lookup cache has 'includeDataInTemplatesAndCloning' as false-> no data will be added.
        # - If the lookup cache has 'includeDataInTemplatesAndCloning' as true: if combined data is <5MB -data will be added otherwise it won't.
        # - Verify the success and error messages.
        # """

        if not is_revision:
            # process next available test type

            if state['current_scenario'][0] >= (total_scenarios) and is_finished_stage1:
                print("finishing all scenarios stage 1.....")
                return {"message_history": [HumanMessage(content="Finished")], "is_scenario_list_processed": True}
            else:
                # move to next available test type
                if (is_finished_stage1):
                    current_scenario = state['scenario_list'][current_scenario[0]]
                    # REFRESH THREAD ID FOR NEW TEST TYPE, ONLY CHAIN LAST TEST TYPE TO PLATFORM FOCUS
                    if state['current_scenario'][0] != (total_scenarios):
                        stage1_thread_id = None

            # query = f"I have uploaded tech design document with details for a back end requirement in PDF format. Can you identify and list down all {current_test_type[1]} cases, based on the uploaded technical document? Please consider all positive, negative and edge cases.  You just need to list down the test case scenarios. Make sure You have the full coverage as per the attached design document. Format the output as JSON, where the key is 'test_list' and the value is a list of dict with Test Name-Details pairs without additional key names. \nInstructions: \n1.  Make sure you generate all the test cases covering all the possible scenarios. \n2. Carefully study the attached document and other Domain information available to you, to generate the test cases. \n3. Be as comprehensive as possible. \n4. Generate 10 or more test cases in each category whenever possible."
            # query = f"I have uploaded tech design document with details for a back end requirement in PDF format. Can you go through it to identify and list down all the {current_test_type[1]} cases, based on the uploaded technical document? Please consider all positive, negative and edge cases.  You just need to list down the test case scenarios. Make sure You have the full coverage as per the attached design document. Format the output as JSON, where the key is 'test_list' and the value is a list of dict with Test Name-Details pairs without additional key names. \nInstructions: \n1. Make sure you generate all the test cases covering all the possible scenarios. \n2. Carefully study and think through the attached document and other Domain information available to you to generate the test cases. \n3. Be as comprehensive as possible. \n4. Generate extensive list of test cases in each category."
            query = get_general_test_case_generation_prompt(current_scenario[1])

        else:
            # Followup question for revision
            query = state['message_history'][-3].content

        json_data = {'input': {'promptInput': {'query': query}}}

        query_message = HumanMessage(content=query)

        if converse_mode and stage1_thread_id is not None:
            json_data['input']['threadID'] = stage1_thread_id
       
        if state.get('attachments'):
            json_data['input']['attachments'] = state['attachments']

        if LOG_LEVEL == "Debug":
            print('-' * 100)
            print(json_data)
            print('-' * 100)

        time.sleep(3)

        # response = requests.post(
        #             "http://localhost:8000/connector/query/invoke",
        #             json = json_data
        # )

        try:

            test_list = self.get_test_schema(state)
            assist = OpenAIAssistantExecuters(agent_id=stage1_assistant_id)
            # out = asyncio.run(assist.get_query_chain(json_data['input']))
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:  # No event loop in this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            out = loop.run_until_complete(assist.get_query_chain(json_data['input']))  # Run async function

            if LOG_LEVEL == "Debug":
                print('+' * 100)
                print(out)
                print('+' * 100)
            # print(out['output']['agent_output']['output'])

            if (out['agent_output'] and out['agent_output']['thread_id']):
                stage1_thread_id = out['agent_output']['thread_id']
                print(stage1_thread_id)
                # print(out['output']['query'])
                # out_apis.append(out['output']['agent_output']['output'])
                out_message = AIMessage(content=out['agent_output']['output'])
                # save json to state
                if out['query'] and out['query'].get('test_list'):
                    print('query')  # ,out['query'])
                    test_list = out['query']['test_list']
                    # prepend index to each test case
                    test_list = [(i + 1, test) for i, test in enumerate(test_list)]
                    out_message = AIMessage(content=str(out['query']))
                else:
                    test_list = [(i + 1, test) for i, test in enumerate(test_list)]
                    out_message = AIMessage(
                        content="**ERROR parsing JSON:** Failed to process output as proper JSON 'test_list' key not found, Received following output response, probably with incorrect JSON.\n" +
                                out['agent_output']['output'])

            # Log usage
            self.cumulative_usage = self._calculate_cumulative_usage(out, self.cumulative_usage)

            # else:
            #     print(response.text)
            #     out_message = AIMessage(content="Sorry, I Failed to retrieve requested information.")

        except Exception as e:
            print("Error assist1: ", e)
            test_list = [(i + 1, test) for i, test in enumerate(test_list)]
            out_message = AIMessage(content="Server error occurred while generating the answer. Prompt to try again.")

        return {"message_history": [query_message, out_message], "test_list": test_list,
                "current_scenario": current_scenario, "current_test": test_list[0]}
    
    # add node which uses subgrph to populate test_types
    def _subgraph_node(self, state: AutoconState):
        # use node from sub_tc_graph.py
        subgraph = SubQAGraph()   
        # prepare graph
        builder = subgraph.prepare_graph()
        subgraph = builder.compile(checkpointer=self.checkpointer)
        
        # Extract the integer index and test details from the tuple
        current_test_index, current_test_details = state['current_test']  # Unpack the tuple
        res = subgraph.invoke({
            "test_list": state['test_list'], 
            "current_test_index": current_test_index, 
            "test_details": current_test_details,
            "attachments": state.get('attachments')  # Pass attachments to the subgraph
        })
        # update state with test_types
        test_list = res['test_list']
        return {"test_list": test_list}

    # assistant for stage2, identify endpoints from resources
    def _assist_stage2_node(self, state: AutoconState):
        if LOG_LEVEL == "Debug":
            print("assist stage2:", type(state), state)
            print(type(state), state)
        global stage2_thread_id
        global stage1_thread_id
        global special_instructions
        # stich with stage1
        stage2_thread_id = stage1_thread_id
        total_tests = len(state['test_list'])
        current_test = state['current_test']
        is_finished_stage2 = state.get('is_finished_stage2')
        is_test_list_processed = state.get('is_test_list_processed')
        print("current_test", current_test[0], current_test, total_tests)
        global user_journey

        # check whether we are revising or processing new resources
        stage2_revisions = state.get('stage2_revisions')
        is_revision = stage2_revisions is not None and stage2_revisions > 0

        if not is_revision:
            # process next available platform feature
            if state['current_test'][0] >= (total_tests) and is_finished_stage2:
                print("finishing all test cases stage 2.....")
                return {"message_history": [HumanMessage(content="Finished")], "is_test_list_processed": True,
                        "current_test": None}
            else:
                # move to next available platform feature
                if (is_finished_stage2):
                    current_test = state['test_list'][current_test[0]]

        # query = f'Could you capture details for following list of test scenarios in JSON as per below format according to the tech design doc I have uploaded? Please do not be leasy and attend to full list of tests along with complete details. Format the output as JSON, where the key is "test_list" and the value is a list of dict with  Test Details JSON without additional key names. \n Note: You have to prepare the complete list for all the test cases, dont leave it incomplete. \nFormat:\nTest Case ID: (give it a logical short name), Title/Description, Preconditions, Test Steps, Test Data, Expected Result, Actual Result, Status, Postconditions, Tags/Labels, Test Type.\nTest List:\n{state["test_list"]}'
        # query = f'I have generated test scenarios for the backend development item. I am attaching tech design document of the same. Could you look at Celigo Product Knoledge, Tech Design and other information in order to generate details for these test scenarios as per given format? Format the output as JSON, where the key is "test_list" and the value is a list of dict with Test Details JSON without additional key names.\nFormat: Test Case ID: (give it a logical short name), Title/Description, Preconditions, Test Steps, Test Data, Expected Result, Actual Result, Status, Postconditions, Tags/Labels, Test Type.\nNote:\n- You have to prepare the complete list for all the test cases, dont leave it incomplete.\n- Just generate requested JSON without any other details, observations or instructions.\nDo not include any additional commentary.\nTest Scenario List:\n{state["test_list"]}'
        if state['tech_stack'] == "Back End":
            query = get_backend_test_case_generation_prompt(current_test[1])
        else:
            query = get_front_end_test_case_generation_prompt(current_test[1])

        if is_revision:
            # Followup question for revision
            # query = state['message_history'][-3].content # original question
            query = state['message_history'][-1].content  # new question

        out_message = None
        test_list = None

        json_data = {'input': {'promptInput': {'query': query}}}

        query_message = HumanMessage(content=query)

        if converse_mode and stage2_thread_id is not None:
            json_data['input']['threadID'] = stage2_thread_id
        if state.get('attachments'):
            json_data['input']['attachments'] = state['attachments']

        if LOG_LEVEL == "Debug":
            print('-' * 100)
            print(json_data)
            print('-' * 100)

        time.sleep(1)

        assist = OpenAIAssistantExecuters(agent_id=stage2_assistant_id)  # "asst_V8DhPI6pYJNS5rMptP4SSr4o")
        try:

            test_list = self.get_test_schema(state)

            # out = asyncio.run(assist.get_query_chain(json_data['input']))
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:  # No event loop in this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            out = loop.run_until_complete(assist.get_query_chain(json_data['input']))  # Run async function

            if (out['agent_output'] and out['agent_output']['thread_id']):
                # save json to state
                if out['query'] and out['query'].get('test_list'):
                    print('query')  # ,out['query'])
                    test_list = out['query']['test_list']
                    # concatenate curent test keys with test details
                    test_list = [({"id": str(current_test[0]), **current_test[1], **test}) for test in test_list]
                    out_message = AIMessage(content=str(out['query']))
                else:
                    test_list = [({"id": str(current_test[0]), **current_test[1], **test}) for test in test_list]
                    out_message = AIMessage(
                        content="**ERROR parsing JSON:** Failed to process output as proper JSON 'test_list' key not found, Received following output response, probably with incorrect JSON.\n" +
                                out['agent_output']['output'])

            # Log usage
            self.cumulative_usage = self._calculate_cumulative_usage(out, self.cumulative_usage)

            # else:
            #     print(response.text)
            #     out_message = AIMessage(content="Sorry, I Failed to retrieve requested information.")

        except Exception as e:
            print("Error assist2: ", e)
            test_list = [({"id": str(current_test[0]), **current_test[1], **test}) for test in test_list]
            out_message = AIMessage(content="Server error occurred while generating the answer. Prompt to try again.")
        return {"message_history": [query_message, out_message], "current_test_details": test_list,
                "current_test": current_test}

    def _qa_agent_reflect_node(self, state: Sequence[BaseMessage]):

        query = (
            "You are a quality assurance engineer. Checking quality of automated extraction generated by LLMs and giving human feedback."
            "Here in this step we are trying to ger full list of resources for Salesforce B2B and D2C Commerce API, starting from 'Commerce Extension Mapping' and ending at 'Commerce Webstore Shipment Items'."
            "Quality check LLM answer given below and generate feedback for the LLM. If you think LLM answer is complete say 'Finished', else generate followup question for the LLM chat session."
            f'\n LLM Answer: "{state[-1].content}"'
            )

        out_message = None

        json_data = {'input': {'promptInput': {'query': query}}}

        if LOG_LEVEL == "Debug":
            print('+' * 100)
            print(json_data)
            print('+' * 100)

        time.sleep(3)

        response = requests.post(
            "http://localhost:8000/connector/query/invoke",
            json=json_data
        )

        if response.status_code == 200:
            # print(response.json())
            out = response.json()
            print(out['output']['agent_output']['output'])

            if (out['output']['agent_output']):
                out_message = HumanMessage(content=out['output']['agent_output']['output'])
        else:
            print(response.text)
            out_message = HumanMessage(content="Sorry, I Failed to retrieve requested information.")

        return out_message

    def _qa_reflection_stage1_node(self, state: AutoconState):
        # print("Reflection_stage1",type(state),state)

        messages = state['message_history']
        print("reflection stage1 messages:", messages)
        # Filter last two messages from the history
        messages = messages[-2:]

        with get_openai_callback() as cb:
            res = qa_reflect_stage1.invoke({"messages": messages})

        # Log usage
        self.cumulative_usage_reflection = self._calculate_cumulative_usage_reflection(cb,
                                                                                       self.cumulative_usage_reflection)

        # We treat the output of this as human feedback for the generator
        parser = JsonOutputToolsParser(return_id=True)

        tool_invocation: AIMessage = res
        parsed_tool_calls = parser.invoke(tool_invocation)
        print('+' * 100)
        print("parsed reflection:", type(parsed_tool_calls))
        pprint(parsed_tool_calls)
        print('+' * 100)

        is_finished = parsed_tool_calls[0]['args']['Finished']
        followup_question = parsed_tool_calls[0]['args'].get(
            'follow_up_question', 
            "PLEASE RETRY THE TASK. "
        )

        # Update revision count
        revisions = state.get('stage1_revisions', 0)
        question = None

        is_test_list_processed = None
        is_finished_stage2 = None
        current_test_details = None
        test_details_list = None
        if is_finished:
            # Reset revision count
            revisions = 0
            question = AIMessage(content="Finished generating test case list.")

            # Reset test list processd flag as its next stage
            is_test_list_processed = False
            is_finished_stage2 = False
            current_test_details = None
            test_details_list = "clear"

        else:
            # revise answer with followup question
            revisions = revisions + 1
            question = HumanMessage(content=followup_question)

        # prepare outputs
        # out_state = {"message_history":[question] if question else None,"stage1_revisions":revisions,"is_finished_stage1":[is_finished] if is_finished else None,"is_resources_processed":[is_resources_processed] if is_resources_processed else None}
        out_state = {"message_history": [question], "stage1_revisions": revisions, "is_finished_stage1": is_finished,
                     "is_test_list_processed": is_test_list_processed, "is_finished_stage2": is_finished_stage2,
                     "current_test_details": current_test_details, "test_details_list": test_details_list}
        filtered_state = {k: v for k, v in out_state.items() if v is not None}
        return filtered_state

    def _qa_reflection_stage2_node(self, state: AutoconState):
        # print("Reflection_stage2",type(state),state)

        # Check if we have processed all the test cases
        if state['is_test_list_processed']:
            print("finishing test cases reflection stage 2.....")
            return {"message_history": [HumanMessage(content="Finished")]}

        # Check if we have processed all the resources
        # if state['is_resources_processed']:
        #     print("finishing resources reflection stage 2.....")
        #     return {"message_history":[HumanMessage(content="Finished")]}

        messages = state['message_history']

        # Filter last two messages from the history
        messages = messages[-2:]

        with get_openai_callback() as cb:
            res = qa_reflect_stage1.invoke({"messages": messages})

        # Log usage
        self.cumulative_usage_reflection = self._calculate_cumulative_usage_reflection(cb,
                                                                                       self.cumulative_usage_reflection)

        # We treat the output of this as human feedback for the generator
        parser = JsonOutputToolsParser(return_id=True)

        tool_invocation: AIMessage = res
        parsed_tool_calls = parser.invoke(tool_invocation)
        print('+' * 100)
        print("parsed reflection stage2:", type(parsed_tool_calls))
        pprint(parsed_tool_calls)
        print('+' * 100)

        is_finished = parsed_tool_calls[0]['args']['Finished']
        followup_question = parsed_tool_calls[0]['args'].get(
            'follow_up_question', 
            "PLEASE RETRY THE TASK. "
        )
        print("Stage 2 QA ---->", type(parsed_tool_calls[0]), type(is_finished), is_finished)

        # Update revision count
        revisions = state.get('stage2_revisions', 0)
        question = None
        current_test_details = None
        # is_test_list_processed = False
        if is_finished:
            # Reset revision count
            revisions = 0
            question = AIMessage(content="Finished generating test case details.")
            current_test_details = state['current_test_details']
            # add_testcase_content(state['current_test_type'][1],state['detailed_test_list'])
            # is_test_list_processed = True

        else:
            # revise answer with followup question
            revisions = revisions + 1
            question = HumanMessage(content=followup_question)

        # prepare outputs
        # out_state = {"message_history":[question] if question else None,"stage2_revisions":revisions,"is_finished_stage2":[is_finished] if is_finished else None,"is_endpoints_processed":[is_endpoints_processed] if is_endpoints_processed else None,"current_resource":current_resource if current_resource else None}
        if revisions >= max_revisions:
            # Skip to next test
            is_finished = True
            revisions = 0
            question = AIMessage(
                content="Could not generate test case details after max attempts allowed. Moving on to next test case.")

        out_state = {"message_history": [question], "stage2_revisions": revisions, "is_finished_stage2": is_finished,
                     "test_details_list": current_test_details}
        filtered_state = {k: v for k, v in out_state.items() if v is not None}
        return filtered_state

    def _should_continue_agent(self, state: List[BaseMessage]):
        # If the agent outcome is an AgentFinish, then we return `exit` string
        # This will be used when setting up the graph to define the flow
        if isinstance(state[-1], HumanMessage) and (state[-1].content == "Finished"):
            print("finishing.....")
            return END
        elif len(state) > 2:
            # End after 3 iterations
            return END
        return "assist"

    def _should_continue_stage1_qa(self, state):
        # End if we have processed all the test types    
        is_scenario_list_processed = state.get('is_scenario_list_processed')
        if is_scenario_list_processed:
            print("Finished all test scenarios .....")
            return END

        # Move to next test type if we have finished processing the current test type
        is_finished = state['is_finished_stage1']
        print("Stage 1 finished ---->", is_finished)

        if is_finished:
            print("finishing stage1.....")
            print("\n Test count", len(state['test_list']), state['test_list'])
            # prompt user and ask if they want to continue to next stage
            # user_input = input("Continue to stage2 (y/n): ")

            # if user_input == 'y':
            #     return "assist_stage2"
            # else:
            #     return END
            # go to subgraph node for backend
            if state['tech_stack'] == "Back End":
                return "subgraph_node"
            else:   
                # go to stage2
                return "assist_stage2"            
        elif state['stage1_revisions'] >= max_revisions:
            # End after max iterations
            print("reached max revisions for stage 1")
            return END

        # revise answer with followup question
        return "assist_stage1"

    def _should_continue_stage2_qa(self, state):

        if self._check_limits():
            print("Usage limits exceeded for stage 2")
            user_input = input("Usage limit has exceeded, continue (y/n)?: ")
            if user_input == 'n':
                return END

        # End if we have processed all the platform feature test types   
        is_test_list_processed = state.get('is_test_list_processed')
        if is_test_list_processed:
            print("Finished all test cases for this scenario.....")
            return "assist_stage1"

        # End if we have processed all the resources    
        # is_test_list_processed = state.get('is_test_list_processed')
        # if is_test_list_processed:
        #     print("Finished all test cases.....")
        #     return END
        # TO DO: go to next app
        # return "assist_stage1"

        # check outcomes and promote to Stage 3
        is_finished = state['is_finished_stage2']
        print("Stage 2 Continue ---->", is_finished)

        if is_finished:
            pass
        elif state['stage2_revisions'] >= max_revisions:
            # End after max iterations
            print("reached max revisions for stage 2")
            # Ask user if they want to continue afresh from previous stage
            # user_input = input("Revise from to stage1 (y/n): ")
            # if user_input == 'y':
            #     return "assist_stage1"
            return "assist_stage2"
        # revise answer with followup question
        return "assist_stage2"

    # builder.add_conditional_edges("assist", should_continue)
    # builder.add_edge("reflect", "assist")

    # assist_stage1_node = sim_assist_stage1_node

    def prepare_graph(self) -> StateGraph:
        builder = StateGraph(AutoconState)
        builder.add_node("assist_stage1", self._assist_stage1_node)
        builder.add_node("reflect_stage1", self._qa_reflection_stage1_node)
        builder.add_node("subgraph_node", self._subgraph_node)
        builder.add_node("assist_stage2", self._assist_stage2_node)
        builder.add_node("reflect_stage2", self._qa_reflection_stage2_node)
        # builder.add_node("assist_stage3", assist_stage3_node)
        # builder.add_node("reflect_stage3", qa_reflection_stage3_node)

        builder.set_entry_point("assist_stage1")

        builder.add_edge("assist_stage1", "reflect_stage1")
        builder.add_conditional_edges("reflect_stage1", self._should_continue_stage1_qa)       
        builder.add_edge("subgraph_node", "assist_stage2")
        builder.add_edge("assist_stage2", "reflect_stage2")
        builder.add_conditional_edges("reflect_stage2", self._should_continue_stage2_qa)

        return builder

    def get_memory_graph(self):

        builder = self.prepare_graph()
        self.checkpointer = MemorySaver()
        lc_graph_with_memory = builder.compile(checkpointer=self.checkpointer)

        return lc_graph_with_memory

    # TO DO: this should be for reguler sqlite    
    async def get_sqlite_graph(self):

        builder = self.prepare_graph()
        self.checkpointer = await AsyncSqliteSaver.from_conn_string(self.checkpoint_path)
        lc_graph_with_memory = builder.compile(checkpointer=self.checkpointer)

        return lc_graph_with_memory

    async def aget_sqlite_graph(self):
        builder = self.prepare_graph()

        # Store the async context manager explicitly and use it later
        self.checkpointer_cm = AsyncSqliteSaver.from_conn_string(self.checkpoint_path)  # Stores the context manager
        self.checkpointer = await self.checkpointer_cm.__aenter__()  # Manually enter the async context
        lc_graph_with_memory = builder.compile(checkpointer=self.checkpointer)

        return lc_graph_with_memory  # Ensures checkpointer remains available

    def cleanup(self):

        if os.path.exists(self.checkpoint_path):
            os.remove(self.checkpoint_path)
            print(f"Database '{self.checkpoint_path}' has been deleted.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()

    async def acleanup(self):
        if hasattr(self, "checkpointer"):
            await self.checkpointer_cm.__aexit__(None, None, None)  # Properly close the async resource
        if os.path.exists(self.checkpoint_path):
            os.remove(self.checkpoint_path)
            print(f"Database '{self.checkpoint_path}' has been deleted.")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.acleanup()