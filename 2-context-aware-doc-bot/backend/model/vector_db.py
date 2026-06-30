from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
import uuid
from .openai import generate_embedding
from . import vector_db_client, COLLECTION_NAME

def upload_chunks_to_db(files, repo_id: str):
    points = []

    for file_data in files:
        for chunk in file_data["nodes"]:
            point_id = str(uuid.uuid4())

            embedding = generate_embedding(chunk)

            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "repo_id": repo_id,
                    "file_path": file_data["file_path"],
                    "file_type": file_data["file_type"],
                    "text": chunk
                }
            )
            points.append(point)

    vector_db_client.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=points
    )
    print(f"Successfully indexed {len(points)} chunks for repo: {repo_id}")



def query_repository(query, repo_id: str, top_k: int = 5):
    query_embedding = generate_embedding(query)
    search_result = vector_db_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="repo_id",
                    match=MatchValue(value=repo_id)
                )
            ]
        ),
        limit=top_k
    )
    print(f"Retrieved {len(search_result)} chunks for repo: {repo_id} with top_k={top_k}")

    retrieved_context = []
    for hit in search_result:
        retrieved_context.append({
            "text": hit.payload["text"],
            "file": hit.payload["file_path"]
        })

    return retrieved_context