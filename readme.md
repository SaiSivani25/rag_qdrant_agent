# RAG Qdrant Agent — Document Intelligence Pipeline

A production-ready Retrieval-Augmented Generation (RAG) pipeline on Google Cloud Platform that automatically processes uploaded documents, extracts text via Document AI OCR, embeds it with Vertex AI, stores vectors in Qdrant, and answers natural language queries using Gemini.

---

## Architecture

```
User Upload (PDF/JPEG)
        │
        ▼
┌─────────────────┐
│   Upload API    │  ← Cloud Run (FastAPI)
│  (upload_api/)  │
└────────┬────────┘
         │ stores file
         ▼
┌─────────────────┐
│   GCS Bucket    │  ← rag-qdrantvb-shivani-docs
└────────┬────────┘
         │ Eventarc trigger (object.finalized)
         ▼
┌─────────────────┐
│ Process Document│  ← Cloud Function Gen2 (Python)
│  (processing/)  │
│                 │
│ 1. Document AI  │  ← OCR text extraction
│ 2. Vertex AI    │  ← text-embedding-004 (768 dims)
│ 3. Qdrant       │  ← vector upsert
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  Qdrant Cloud   │  ← Vector DB (Cosine similarity)
│ rag_documents   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Query API     │  ← Cloud Run (FastAPI)
│  (query_api/)   │
│                 │
│ 1. Embed query  │  ← Vertex AI
│ 2. Search       │  ← Qdrant top-k
│ 3. Generate     │  ← Gemini
└─────────────────┘
```

---

## Project Structure

```
Rag_QdrantVB_Shivani/
├── upload_api/
│   ├── main.py              # FastAPI upload endpoint
│   ├── requirements.txt
│   └── Dockerfile
├── processing/
│   ├── main.py              # Cloud Function — OCR + embed + store
│   ├── setup_qdrant.py      # One-time Qdrant collection setup
│   └── requirements.txt
├── query_api/
│   ├── main.py              # FastAPI query endpoint
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
| Vertex AI | Generates text embeddings (`text-embedding-004`) |
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

## Setup & Deployment

### 1. GCP Setup

```bash
# Set project
gcloud config set project YOUR_PROJECT_ID

# Enable APIs
gcloud services enable storage.googleapis.com documentai.googleapis.com \
  aiplatform.googleapis.com run.googleapis.com eventarc.googleapis.com

# Create GCS bucket
gcloud storage buckets create gs://YOUR_BUCKET \
  --location=us-central1 --uniform-bucket-level-access

# Create service account
gcloud iam service-accounts create rag-document-sa \
  --display-name "RAG Document Agent Service Account"

# Grant permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/documentai.apiUser"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

### 2. Qdrant Setup

```bash
cd processing
python setup_qdrant.py
```

### 3. Deploy Upload API

```bash
cd upload_api
gcloud run deploy upload-api \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --service-account=rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars="GCS_BUCKET_NAME=YOUR_BUCKET,GCP_PROJECT_ID=YOUR_PROJECT_ID" \
  --min-instances=0 --max-instances=1
```

### 4. Deploy Processing Cloud Function

```bash
cd processing
gcloud functions deploy process-document \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=process_document \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=YOUR_BUCKET" \
  --service-account=rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=us-central1,DOCAI_PROCESSOR_ID=YOUR_PROCESSOR_ID,DOCAI_LOCATION=us,QDRANT_URL=YOUR_QDRANT_URL,QDRANT_API_KEY=YOUR_QDRANT_KEY" \
  --memory=2Gi --timeout=300s
```

### 5. Deploy Query API

```bash
cd query_api
gcloud run deploy query-api \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --service-account=rag-document-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars="GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=us-central1,QDRANT_URL=YOUR_QDRANT_URL,QDRANT_API_KEY=YOUR_QDRANT_KEY,GEMINI_API_KEY=YOUR_GEMINI_KEY" \
  --min-instances=0 --max-instances=1
```

---

## Usage

### Upload a Document

```powershell
# PowerShell
Add-Type -AssemblyName System.Net.Http
$client = [System.Net.Http.HttpClient]::new()
$form = [System.Net.Http.MultipartFormDataContent]::new()
$fileStream = [System.IO.File]::OpenRead("path/to/document.pdf")
$fileContent = [System.Net.Http.StreamContent]::new($fileStream)
$fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new("application/pdf")
$form.Add($fileContent, "file", "document.pdf")
$response = $client.PostAsync("https://YOUR_UPLOAD_API/upload", $form).Result
Write-Host $response.Content.ReadAsStringAsync().Result
```

### Query the RAG System

```powershell
Invoke-RestMethod `
  -Uri "https://YOUR_QUERY_API/query" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"question": "What is artificial intelligence?"}'
```

### Check Qdrant Collection

```powershell
curl.exe -X GET "https://YOUR_QDRANT_URL/collections/rag_documents" `
  -H "api-key: YOUR_QDRANT_API_KEY"
```

---

## Supported File Types

| Type | MIME Type |
|---|---|
| PDF | `application/pdf` |
| JPEG | `image/jpeg` |

---

## Sample Documents

The pipeline has been tested with the following document types:
- AI & Machine Learning (Artificial Intelligence, AI Agents, Generative AI, Neural Networks)
- Science (Black Holes, Human Genome)
- Medicine (Human Anatomy, Human Brain)
- History (World War 1, World War 2)
- Economics (Technological Unemployment)

---
