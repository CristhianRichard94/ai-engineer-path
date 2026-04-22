from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from LLM import query_openai_api

app = FastAPI()

class MessageRequest(BaseModel):
    conversation: list

# CORS configuration
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/")
def root():
    return {"message": "Hello from the backend!"}

@app.post("/api/message")
async def post_message(request: MessageRequest):
    try:
        conversation = request.conversation
        response = query_openai_api(conversation)
        return {"content": response}
    except Exception as e:
        print(f"Error occurred: {e}")
        return {"error": "An error occurred while processing the request."}, 500