from fastapi import Body, FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
import shutil
import os
from backend.ingestor.content_ingestor import ContentIngestor
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Personal Learning Portal API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Or specify your frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize our ingestor
# This creates a single instance that lives as long as the API server is running
ingestor = ContentIngestor()

# Create a temporary directory for file uploads
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# class YouTubeRequest(BaseModel):
#     url: str

# @app.post("/ingest-youtube/")
# async def ingest_youtube(request: YouTubeRequest):
#     """Endpoint to ingest a YouTube video from its URL."""
#     if not request.url:
#         raise HTTPException(status_code=400, detail="YouTube URL is required.")
#
#     try:
#         chunks_ingested = ingestor.ingest_youtube_video(request.url)
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Error ingesting YouTube video: {str(e)}")
#
#     if chunks_ingested > 0:
#         return {"status": "success", "chunks_ingested": chunks_ingested, "source": request.url}
#     else:
#         raise HTTPException(status_code=500, detail="Failed to ingest YouTube video.")

class TextIngestRequest(BaseModel):
    text: str
    source_identifier: str = "manual_text"

@app.post("/ingest-text/")
async def ingest_text(request: TextIngestRequest = Body(...)):
    """Endpoint to ingest pasted text."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is required.")

    try:
        chunks_ingested = ingestor.ingest_text(request.text, request.source_identifier)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error ingesting text: {str(e)}")

    if chunks_ingested > 0:
        return {
            "status": "success",
            "chunks_ingested": chunks_ingested,
            "source": request.source_identifier
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to ingest text.")

@app.post("/ingest-pdf/")
async def ingest_pdf(file: UploadFile = File(...)):
    """Endpoint to ingest a PDF file."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    # Save the uploaded file temporarily
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    chunks_ingested = ingestor.ingest_pdf(file_path)

    # Clean up the temporary file
    os.remove(file_path)

    if chunks_ingested > 0:
        return {"status": "success", "chunks_ingested": chunks_ingested, "source": file.filename}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to ingest PDF: {file.filename}")


@app.get("/")
def read_root():
    return {"message": "Welcome to the Personal Learning Portal API!"}