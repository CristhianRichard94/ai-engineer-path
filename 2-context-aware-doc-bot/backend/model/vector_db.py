from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
import uuid
from tqdm import tqdm
from services.llm import generate_embedding
from . import vector_db_client, COLLECTION_NAME

def upload_chunks_to_db(files, repo_id: str):
    points = []
    all_chunks = [
        (file_data, chunk)
        for file_data in files
        for chunk in file_data["nodes"]
    ]

    for file_data, chunk in tqdm(all_chunks, desc="Embedding chunks", unit="chunk"):
        text = chunk
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=generate_embedding(text),
            payload={
                "repo_id": repo_id,
                "file_path": file_data["file_path"],
                "file_type": file_data["file_type"],
                "text": text
            }
        )
        points.append(point)

    if not points:
        print(f"No chunks to index for repo: {repo_id}")
        return

    vector_db_client.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=points
    )
    print(f"Successfully indexed {len(points)} chunks for repo: {repo_id}")



def is_repo_indexed(repo_id: str) -> bool:
    result = vector_db_client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]),
        limit=1,
    )
    return len(result[0]) > 0


def query_repository(query, repo_id: str, top_k: int = 5):
    query_embedding = generate_embedding(query)
    result = vector_db_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
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
    search_result = result.points
    print(f"Retrieved {len(search_result)} chunks for repo: {repo_id} with top_k={top_k}")

    retrieved_context = []
    for hit in search_result:
        retrieved_context.append({
            "text": hit.payload["text"],
            "file": hit.payload["file_path"]
        })

    return retrieved_context