# NyayaSathi AI — Full Hackathon Build

A complete MVP for an AI-based interactive chatbot / virtual assistant for justice-service navigation.

## Stack
- Frontend: HTML/CSS/JavaScript (easy to migrate to React / Next.js)
- Backend: Python FastAPI
- Retrieval: Scikit-Learn TF-IDF + cosine similarity
- Database: SQLite by default, PostgreSQL supported
- PDF ingestion: PyPDF
- Image preprocessing: OpenCV
- Optional generative layer: OpenAI-compatible LLM endpoint

## Major features
- English, Hindi and Kannada UI
- Voice input where browser SpeechRecognition is supported
- Verified source display on each answer
- Conversation history per browser session
- Helpful / not-helpful feedback
- Admin analytics dashboard
- Knowledge upload for PDF/TXT/MD files
- Dynamic chunking and retrieval of uploaded documents
- OpenCV preprocessing for scanned document images
- CSV export of chat analytics
- Optional PostgreSQL
- Optional LLM grounded only on retrieved context
- Privacy warnings and safe fallback behavior

## Run locally

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env`.

Then:

```bash
uvicorn app:app --reload
```

Open:
- Citizen app: http://127.0.0.1:8000
- Admin: http://127.0.0.1:8000/admin

Default demo admin credentials:
- Username: admin
- Password: change-me

Change them in `.env` before deployment.

## PostgreSQL

Set:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/nyayasathi
```

## Optional LLM

Set:

```env
LLM_API_KEY=your_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=your_supported_model
```

Without an LLM key, the system still works using Scikit-Learn TF-IDF retrieval.

## Admin document ingestion

Go to `/admin`, sign in, then upload:
- PDF
- TXT
- MD

Each document is split into retrieval chunks and stored in the database.

## OpenCV document preprocessing

The admin page also includes an image preprocessing utility. It converts a scanned/image document to grayscale and adaptive-thresholded PNG, which can be fed into a separate OCR pipeline if needed.

## Important production note

This is a hackathon/educational prototype and is not an official Government of India service. Before production use, add approved-source ingestion, robust authentication/RBAC, encrypted persistent sessions, rate limiting, CSRF/CSP/WAF protections, privacy and retention controls, accessibility review, legal review, human escalation, audit logging, monitoring, and formal authorization for government branding/integrations.
