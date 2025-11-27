import os
from openai import OpenAI

class SimpleAssistantThreadManager:
    def __init__(self, assistant_id: str):
        """
        Initialize the assistant thread manager with the given assistant ID.

        Parameters
        ----------
        assistant_id : str
            The ID of the assistant to manage threads for.
        """
        self.assistant_id = assistant_id
        self.thread_id = None
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    def start_thread(self):
        """Start a new thread if one doesn't already exist."""
        if self.thread_id is None:
            response = self.client.beta.threads.create()
            self.thread_id = response.id
            print(f"Started new thread with ID: {self.thread_id}")
        else:
            print(f"Using existing thread ID: {self.thread_id}")

    def invoke_assistant(self, input_data: dict):
        """
        Invoke the assistant with the given input data, using the current thread.

        Parameters
        ----------
        input_data : dict
            The input data to send to the assistant.

        Returns
        -------
        dict
            The assistant's response.
        """
        if self.thread_id is None:
            self.start_thread()

        input_data['threadID'] = self.thread_id
        response = self.client.beta.threads.messages.create(
            thread_id=self.thread_id,
            role="user",
            content=input_data
        )
        return response

# Example usage
# manager = SimpleAssistantThreadManager(assistant_id="asst_h4iaXXErEoKs7JUvZSJY6CZe")
# manager.start_thread()
# response = manager.invoke_assistant({"promptInput": "Hello, assistant!"})
# print(response)
