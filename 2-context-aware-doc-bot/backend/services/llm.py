from . import openai
from logger import get_logger

log = get_logger()


def llm_prompt(prompt, model="gpt-4", temperature=0.7, top_p=1):
    response = openai.responses.create(
        model,
        input=prompt,
        temperature=temperature,
        top_p=top_p,
    )
    return response.output_text


def llm_prompt_stream(prompt, model="gpt-4", temperature=0.7, top_p=1):
    """Stream text deltas from the OpenAI Responses API as they arrive.

    Yields plain text chunks (str). Defensive against SDK event-schema
    variations: unknown event types are logged and skipped rather than
    raising. Raises on a genuine stream-level error/exception so the
    caller (Flask route) can surface it as a final SSE error event.
    """
    stream = openai.responses.create(
        model=model,
        input=prompt,
        temperature=temperature,
        top_p=top_p,
        stream=True,
    )

    for event in stream:
        event_type = getattr(event, "type", None)

        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", "")
            if delta:
                yield delta
        elif event_type == "response.completed":
            return
        elif event_type in ("error", "response.failed"):
            message = getattr(event, "message", None)
            if not message:
                response_obj = getattr(event, "response", None)
                error_obj = getattr(response_obj, "error", None) if response_obj else None
                message = getattr(error_obj, "message", None) if error_obj else None
            if not message:
                message = "unknown error during response stream"
            raise RuntimeError(message)
        else:
            log.info("unhandled response stream event type: %s", event_type)


def generate_embedding(text: str):
    # In a real app, you would call an embedding model here
    embedding = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return embedding.data[0].embedding
