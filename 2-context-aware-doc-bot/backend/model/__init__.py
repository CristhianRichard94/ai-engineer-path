from dotenv import load_dotenv
load_dotenv()

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType
from config import settings

vector_db_client = QdrantClient(url=settings.qdrant_uri, api_key=settings.qdrant_api_key or None)

if not vector_db_client.collection_exists(collection_name=settings.qdrant_collection):
    vector_db_client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(size=settings.qdrant_vector_size, distance=Distance.COSINE),
    )

vector_db_client.create_payload_index(
    collection_name=settings.qdrant_collection,
    field_name="repo_id",
    field_schema=PayloadSchemaType.KEYWORD,
)
COLLECTION_NAME = settings.qdrant_collection
