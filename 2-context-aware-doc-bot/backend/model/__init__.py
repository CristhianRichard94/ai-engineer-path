import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from openai import OpenAI

load_dotenv()
COLLECTION_NAME = "github_repos"
QDRANT_URI = os.getenv("QDRANT_URI")
vector_db_client = QdrantClient(url=QDRANT_URI)
openai_api_key = os.getenv("OPENAI_API_KEY")


if not vector_db_client.collection_exists(collection_name=COLLECTION_NAME):
    vector_db_client.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )

openai = OpenAI(api_key=openai_api_key)
