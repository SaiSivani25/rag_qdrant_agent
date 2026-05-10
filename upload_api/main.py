import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from google.api_core.exceptions import GoogleAPIError
from google.cloud import storage

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI()

BUCKET_NAME = os.environ["GCS_BUCKET_NAME"]
storage_client = storage.Client(project=os.environ["GCP_PROJECT_ID"])


@app.get("/health")
def health():
    results = {}
    overall = "ok"

    start = time.monotonic()
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        bucket.reload()
        results["gcs"] = {
            "status": "ok",
            "latency_ms": round((time.monotonic() - start) * 1000),
        }
    except GoogleAPIError as e:
        results["gcs"] = {
            "status": "down",
            "error": str(e),
            "latency_ms": round((time.monotonic() - start) * 1000),
        }
        overall = "down"
    except Exception as e:
        results["gcs"] = {
            "status": "down",
            "error": str(e),
            "latency_ms": round((time.monotonic() - start) * 1000),
        }
        overall = "down"

    return JSONResponse(
        status_code=503 if overall == "down" else 200,
        content={"status": overall, "api": "upload-api", "services": results},
    )


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if file.content_type not in ("application/pdf", "image/jpeg"):
        raise HTTPException(
            status_code=400, detail="Only PDF and JPEG files are accepted."
        )

    ext = "pdf" if file.content_type == "application/pdf" else "jpg"
    file_id = str(uuid.uuid4())
    blob_name = f"{file_id}.{ext}"

    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(blob_name)
    blob.upload_from_file(file.file, content_type=file.content_type)

    file_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"
    return {"fileId": file_id, "fileURL": file_url}
