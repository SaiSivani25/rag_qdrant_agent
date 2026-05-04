import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from google.cloud import storage

# Load .env only if running locally
if os.path.exists(Path(__file__).resolve().parent / ".env"):
    load_dotenv(Path(__file__).resolve().parent / ".env")

app = FastAPI()

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")

if not BUCKET_NAME or not PROJECT_ID:
    raise RuntimeError("GCS_BUCKET_NAME and GCP_PROJECT_ID must be set")

storage_client = storage.Client(project=PROJECT_ID)


@app.get("/health")
def health():
    return {"status": "ok"}


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
