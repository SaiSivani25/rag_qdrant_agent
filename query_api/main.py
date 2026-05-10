import json
import os
import time
from pathlib import Path
from typing import AsyncGenerator

import vertexai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from google import genai
from google.genai import types
from pydantic import BaseModel
from qdrant_client import QdrantClient
from vertexai.language_models import TextEmbeddingModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCP_REGION = os.environ["GCP_REGION"]
QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ["QDRANT_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
COLLECTION_NAME = "rag_documents"

vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
embed_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
genai_client = genai.Client(api_key=GEMINI_API_KEY)
qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

app = FastAPI()


def _ms(start: float) -> int:
    return round((time.monotonic() - start) * 1000)


def _degrade(current: str) -> str:
    return "degraded" if current == "ok" else "down"


@app.get("/health")
def health():
    results = {}
    overall = "ok"

    start = time.monotonic()
    try:
        embed_model.get_embeddings(["health check probe"])
        results["vertex_ai"] = {"status": "ok", "latency_ms": _ms(start)}
    except Exception as e:
        results["vertex_ai"] = {
            "status": "down",
            "error": str(e),
            "latency_ms": _ms(start),
        }
        overall = _degrade(overall)

    start = time.monotonic()
    try:
        qdrant.get_collection(COLLECTION_NAME)
        results["qdrant"] = {"status": "ok", "latency_ms": _ms(start)}
    except Exception as e:
        results["qdrant"] = {
            "status": "down",
            "error": str(e),
            "latency_ms": _ms(start),
        }
        overall = _degrade(overall)

    start = time.monotonic()
    try:
        genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents="ping",
            config=types.GenerateContentConfig(max_output_tokens=1),
        )
        results["gemini"] = {"status": "ok", "latency_ms": _ms(start)}
    except Exception as e:
        results["gemini"] = {
            "status": "down",
            "error": str(e),
            "latency_ms": _ms(start),
        }
        overall = _degrade(overall)

    return JSONResponse(
        status_code=503 if overall == "down" else 200,
        content={"status": overall, "api": "query-api", "services": results},
    )


class QueryRequest(BaseModel):
    question: str
    stream: bool = False


def _retrieve(question: str):
    question_vector = embed_model.get_embeddings([question])[0].values
    results = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=question_vector,
        limit=3,
        with_payload=True,
    )
    if not results:
        raise HTTPException(status_code=404, detail="No relevant documents found.")
    return results


def _build_prompt(question: str, results) -> str:
    context = ""
    for result in results:
        context += f"\n--- Page {result.payload['page_number']} from {result.payload['fileURL']} ---\n"
        context += result.payload["text"] + "\n"
    return f"""You are a helpful assistant. Answer the question using ONLY the context provided below.
If the answer is not in the context, say "I could not find relevant information in the documents."

Context:
{context}

Question: {question}
Answer:"""


def _build_sources(results) -> list:
    return [
        {
            "page_number": r.payload["page_number"],
            "fileURL": r.payload["fileURL"],
            "relevance_score": round(r.score, 4),
        }
        for r in results
    ]


async def _stream_response(question: str) -> AsyncGenerator[str, None]:
    try:
        results = _retrieve(question)
        prompt = _build_prompt(question, results)
        sources = _build_sources(results)

        response = genai_client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=1024,
            ),
        )

        for chunk in response:
            if chunk.text:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.text})}\n\n"

        yield f"data: {json.dumps({'type': 'sources', 'content': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except HTTPException as e:
        yield f"data: {json.dumps({'type': 'error', 'content': e.detail})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


@app.post("/query")
async def query(request: QueryRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if request.stream:
        return StreamingResponse(
            _stream_response(question),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    results = _retrieve(question)
    prompt = _build_prompt(question, results)
    response = genai_client.models.generate_content(
        model="gemini-2.5-flash", contents=prompt
    )

    return {
        "query": question,
        "answer": response.text.strip(),
        "source_pages": _build_sources(results),
    }
