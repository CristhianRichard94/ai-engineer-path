from . import openai




def prompt(prompt, document):
    combined_input = f"{prompt}\n\n{document}"
    response = openai.responses.create(
        model="gpt-4",
        input=combined_input,
        temperature=0.7,
        top_p=1,
    )
    return response.output_text


def generate_embedding(text: str):
    # In a real app, you would call an embedding model here
    embedding = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return embedding

