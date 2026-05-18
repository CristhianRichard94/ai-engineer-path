



from dotenv import load_dotenv
import os
from openai import OpenAI

load_dotenv()
client = OpenAI()

openai_api_key = os.getenv("OPENAI_API_KEY")



def prompt_ia(prompt, document):
    combined_input = f"{prompt}\n\n{document}"
    response = client.responses.create(
        model="gpt-4",
        input=combined_input,
        temperature=0.7,
        top_p=1,
    )
    return response.output_text
