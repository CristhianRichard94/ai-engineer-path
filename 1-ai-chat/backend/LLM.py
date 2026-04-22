from dotenv import load_dotenv
import os
from openai import OpenAI

load_dotenv()
client = OpenAI()

openai_api_key = os.getenv("OPENAI_API_KEY")


def query_openai_api(messages):
    text_response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        max_tokens=4096,
        temperature=0.7,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    return text_response.choices[0].message.content
