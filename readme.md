# RAG Qdrant Agent — Document Intelligence Pipeline

A production-ready Retrieval-Augmented Generation (RAG) pipeline on Google Cloud Platform that automatically processes uploaded documents, extracts text via Document AI OCR, embeds it with Vertex AI, stores vectors in Qdrant, and answers natural language queries using Gemini — with real-time streaming responses.

---

## What's New

- **Deep health checks** — every API probes its dependencies with real calls, returning per-service status and latency
- **Resilient processing** — per-batch retry with exponential backoff, idempotent point IDs, graceful handling of image-only pages
- **SSE streaming** — query responses stream token by token in real time, exactly like ChatGPT

---

## Architecture

```
User Upload (PDF/JPEG)
        │
        ▼
┌─────────────────┐
│   Upload API    │  ← Cloud Run (FastAPI)
│  (upload_api/)  │
│  GET /health    │  ← probes GCS bucket
└────────┬────────┘
         │ stores file
         ▼
┌─────────────────┐
│   GCS Bucket    │  ← rag-qdrantvb-shivani-docs
└────────┬────────┘
         │ Eventarc trigger (object.finalized)
         ▼
┌──────────────────────────┐
│   Process Document       │  ← Cloud Function Gen2 (Python)
│   (processing/)          │
│                          │
│ 1. Document AI OCR       │  ← text extraction, skip image-only pages
│ 2. Vertex AI Embeddings  │  ← batches of 5, retry 2s/10s/30s backoff
│ 3. Qdrant batch upsert   │  ← idempotent IDs, 5 points per call
└──────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Qdrant Cloud   │  ← Vector DB (Cosine similarity)
│ rag_documents   │
└────────┬────────┘
         │
         ▼
┌──────────────────────────┐
│   Query API              │  ← Cloud Run (FastAPI)
│   (query_api/)           │
│   GET /health            │  ← probes Vertex AI + Qdrant + Gemini
│                          │
│ 1. Embed query           │  ← Vertex AI
│ 2. Search                │  ← Qdrant top-3
│ 3. Generate              │  ← Gemini 2.5 Flash
│ 4. Stream or full JSON   │  ← SSE token/sources/done events
└──────────────────────────┘
```

---

## Project Structure

```
Rag_QdrantVB_Shivani/
├── upload_api/
│   ├── main.py              # FastAPI upload + deep health check
│   ├── requirements.txt
│   └── Dockerfile
├── processing/
│   ├── main.py              # Resilient Cloud Function pipeline
│   ├── setup_qdrant.py      # One-time Qdrant collection setup
│   └── requirements.txt
├── query_api/
│   ├── main.py              # FastAPI query (streaming + non-streaming)
│   ├── requirements.txt
│   └── Dockerfile
├── document_rag_text/       # Sample PDFs (not committed)
├── .gitignore
└── README.md
```

---

## GCP Services Used

| Service | Purpose |
|---|---|
| Cloud Run | Hosts Upload API and Query API |
| Cloud Functions (Gen2) | Event-driven document processing |
| Cloud Storage | Stores uploaded documents |
| Document AI (OCR) | Extracts text from PDFs and images |
| Vertex AI | Generates text embeddings (text-embedding-004) |
| Eventarc | Triggers Cloud Function on GCS upload |
| Artifact Registry | Stores Docker container images |
| Cloud Build | Builds containers on deploy |

---

## Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- Python 3.11+
- Qdrant Cloud account
- Google AI Studio API key (Gemini)
- **Windows: use Command Prompt (cmd), not PowerShell**

---

## Environment Variables

Create a `.env` file at the project root (never commit this):

```env
GCS_BUCKET_NAME=your-bucket-name
GCP_PROJECT_ID=your-project-id
GCP_PROJECT_NUMBER=your-project-number
GCP_REGION=us-central1
DOCAI_PROCESSOR_ID=your-processor-id
DOCAI_LOCATION=us
VERTEX_AI_LOCATION=us-central1
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key
GEMINI_API_KEY=your-gemini-api-key
UPLOAD_API_URL=https://your-upload-api.run.app
```

---

## Setup & Deployment (Windows — use cmd)

### 1. GCP Setup

```cmd
gcloud config set project YOUR_PROJECT_ID

gcloud services enable storage.googleapis.com documentai.googleapis.com aiplatform.googleapis.com run.googleapis.com eventarc.googleapis.com cloudfunctions.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud storage buckets create gs://YOUR_BUCKET --location=us-central1 --uniform-bucket-level-access

gcloud iam service-accounts create rag-document-sa --display-name "RAG Document Agent Service Account"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" --role="roles/storage.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" --role="roles/documentai.apiUser"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" --role="roles/eventarc.eventReceiver"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" --role="roles/run.invoker"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" --role="roles/logging.logWriter"
```

### 2. Eventarc Permissions

```cmd
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:service-YOUR_PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com" --role="roles/pubsub.publisher"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:service-YOUR_PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" --role="roles/iam.serviceAccountTokenCreator"
```

### 3. Document AI Processor

1. GCP Console → Document AI → Explore Processors
2. Create → Document OCR → Region: `us`
3. Copy the Processor ID to your `.env`

### 4. Qdrant Setup

1. [cloud.qdrant.io](https://cloud.qdrant.io) → create free cluster
2. Copy URL and API key to `.env`
3. Run collection setup from cmd:

```cmd
cd processing
python setup_qdrant.py
```

### 5. Virtual Environment (Windows)

```cmd
python -m venv rag_agent
rag_agent\Scripts\activate.bat
```

### 6. Deploy Upload API

```cmd
cd upload_api
gcloud run deploy upload-api --source . --region us-central1 --allow-unauthenticated --set-env-vars "GCS_BUCKET_NAME=YOUR_BUCKET,GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=us-central1"
```

### 7. Deploy Processing Pipeline

```cmd
cd processing
gcloud functions deploy process-document --gen2 --runtime=python311 --region=us-central1 --source=. --entry-point=process_document --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" --trigger-event-filters="bucket=YOUR_BUCKET_NAME" --memory=2Gi --timeout=300s --set-env-vars "GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=us-central1,GCS_BUCKET_NAME=YOUR_BUCKET,DOCAI_PROCESSOR_ID=YOUR_PROCESSOR_ID,DOCAI_LOCATION=us,QDRANT_URL=YOUR_QDRANT_URL,QDRANT_API_KEY=YOUR_QDRANT_KEY"
```

### 8. Deploy Query API

```cmd
cd query_api
gcloud run deploy query-api --source . --region us-central1 --allow-unauthenticated --set-env-vars "GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=us-central1,QDRANT_URL=YOUR_QDRANT_URL,QDRANT_API_KEY=YOUR_QDRANT_KEY,GEMINI_API_KEY=YOUR_GEMINI_KEY"
```

---

## API Reference

### Upload API

**GET /health** — deep health check, probes GCS bucket

```cmd
curl https://YOUR_UPLOAD_API_URL/health
```

```json
{
  "status": "ok",
  "api": "upload-api",
  "services": {
    "gcs": { "status": "ok", "latency_ms": 92 }
  }
}
```

**POST /upload**

```cmd
curl -X POST https://YOUR_UPLOAD_API_URL/upload -F "file=@C:\path\to\document.pdf"
```

```json
{
  "fileId": "uuid-here",
  "fileURL": "https://storage.googleapis.com/bucket/uuid-here.pdf"
}
```

---

### Query API

**GET /health** — deep health check, probes Vertex AI + Qdrant + Gemini

```cmd
curl https://YOUR_QUERY_API_URL/health
```

```json
{
  "status": "ok",
  "api": "query-api",
  "services": {
    "vertex_ai": { "status": "ok", "latency_ms": 345 },
    "qdrant":    { "status": "ok", "latency_ms": 176 },
    "gemini":    { "status": "ok", "latency_ms": 435 }
  }
}
```

Status values: `ok` / `degraded` / `down`. HTTP 503 when any service is `down`.

**POST /query — non-streaming**

```cmd
curl -X POST https://YOUR_QUERY_API_URL/query -H "Content-Type: application/json" -d "{\"question\": \"What is machine learning?\", \"stream\": false}"
```

```json
{
  "query": "What is machine learning?",
  "answer": "Machine learning is a technique by which...",
  "source_pages": [
    {
      "page_number": 9,
      "fileURL": "https://storage.googleapis.com/bucket/uuid.pdf",
      "relevance_score": 0.6559
    }
  ]
}
```

**POST /query — streaming (SSE)**

```cmd
curl -X POST https://YOUR_QUERY_API_URL/query -H "Content-Type: application/json" -H "Accept: text/event-stream" -d "{\"question\": \"What is machine learning?\", \"stream\": true}" --no-buffer
```

```
data: {"type": "token",   "content": "Machine learning is"}
data: {"type": "token",   "content": " a technique by which..."}
data: {"type": "sources", "content": [{...}]}
data: {"type": "done"}
```

Three event types: `token` — append to answer, `sources` — render citations, `done` — close connection.

---

## Processing Pipeline — Resilience Details

| Feature | Detail |
|---|---|
| Batch size | 5 pages per Vertex AI call, 5 points per Qdrant upsert |
| Retry policy | 3 attempts per batch — 2s → 10s → 30s backoff |
| Failure isolation | One batch fails → others continue, partial results saved |
| Idempotency | Point ID = hash(fileId + page_number) — re-runs never duplicate |
| Image-only pages | Detected by char count < 20, skipped gracefully with log |

---

## End-to-End Test (Windows cmd)

```cmd
:: 1. Upload a PDF
curl -X POST https://YOUR_UPLOAD_API_URL/upload -F "file=@C:\path\to\document.pdf"

:: 2. Wait 30-60 seconds for processing

:: 3. Query with streaming
curl -X POST https://YOUR_QUERY_API_URL/query -H "Content-Type: application/json" -H "Accept: text/event-stream" -d "{\"question\": \"Your question here\", \"stream\": true}" --no-buffer

:: 4. Check processing logs
gcloud functions logs read process-document --region=us-central1 --limit=20
```

---

## Notes

- Document AI free tier: 15 pages per request. Trim large PDFs to 10 pages before uploading.
- Qdrant free tier: 1GB storage — sufficient for hundreds of documents.
- All Cloud Run services scale to zero when idle — no idle costs.
- Always use **cmd** on Windows, not PowerShell — curl flags like `-X`, `-H`, `-F` are intercepted by PowerShell.
- The `X-Accel-Buffering: no` header on the Query API disables nginx buffering on Cloud Run, required for SSE streaming to work correctly.
