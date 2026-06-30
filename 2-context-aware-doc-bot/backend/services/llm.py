from . import openai




def llm_prompt(prompt, model="gpt-4", temperature=0.7, top_p=1):
    response = openai.responses.create(
        model,
        input=prompt,
        temperature=temperature,
        top_p=top_p,
    )
    return response.output_text


def generate_embedding(text: str):
    # In a real app, you would call an embedding model here
    embedding = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return embedding.data[0].embedding

