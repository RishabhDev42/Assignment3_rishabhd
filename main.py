from fastapi import Body, Depends, FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
import shutil
import os
import dotenv
from pymilvus import connections, Collection, MilvusClient
from sqlalchemy.future import select

from backend.agents.learning_navigator_agent import LearningNavigatorAgent
from backend.agents.summay_agent import SummaryAgent
from backend.agents.trainer_agent import TrainerAgent
from backend.ingestor.content_ingestor import ContentIngestor
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from backend.db.database import AsyncSessionLocal, engine, Base
from backend.db.models import ConversationHistory, LearningTopic
from sqlalchemy.ext.asyncio import AsyncSession
from backend import assessment_router

# This section runs once when the app starts
dotenv.load_dotenv()
# Connect to Milvus
client = MilvusClient()
connections.connect()
milvus_collection = Collection("learning_portal")
milvus_collection.load()

# Instantiate agents
trainer_agent = TrainerAgent(milvus_collection=milvus_collection)
summary_agent = SummaryAgent()
navigator_agent = LearningNavigatorAgent()
from backend.db.deps import get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created.")
    yield

app = FastAPI(title="Personal Learning Portal API", lifespan=lifespan)

app.include_router(assessment_router.router)

@app.post("/add-message/")
async def add_message(content: str, sender: str, db: AsyncSession = Depends(get_db)):
    """
    An example endpoint to add a new message to the conversation history.
    """
    new_message = ConversationHistory(sender=sender, content=content)
    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)
    return new_message


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

class ChatRequest(BaseModel):
    """Request model for a user's chat message."""
    content: str

class ChatResponse(BaseModel):
    """Response model for the AI's answer and suggestions."""
    answer: str
    suggestions: list[str]


@app.post("/chat/", response_model=ChatResponse)
async def handle_chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Main endpoint to handle a user's chat message.
    """
    try:
        # 1. Save the user's message to the database
        user_message = ConversationHistory(sender="user", content=request.content)
        db.add(user_message)
        await db.commit()
        await db.refresh(user_message)

        # 2. Get the AI's answer using the Trainer Agent
        print("Getting response from Trainer Agent...")
        ai_answer = await trainer_agent.answer_query(db=db, user_query=request.content)

        # 3. Save the AI's response to the database
        ai_message = ConversationHistory(sender="portal", content=ai_answer)
        db.add(ai_message)
        await db.commit()
        await db.refresh(ai_message)

        # 4. Get next-step suggestions from the Learning Navigator
        print("Getting suggestions from Navigator Agent...")
        suggestions = await navigator_agent.suggest_next_steps(db=db)

        # 5. Check if we should trigger the Summary Agent
        result = await db.execute(select(ConversationHistory))
        total_messages = len(result.scalars().all())

        if total_messages % 10 == 0:  # Trigger every 10 messages
            print("Triggering Summary Agent in the background...")
            await summary_agent.summarize_conversation(db=db)

        return ChatResponse(answer=ai_answer, suggestions=suggestions)

    except Exception as e:
        print(f"An error occurred in the chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred.")
@app.get("/")
def read_root():
    return {"message": "Welcome to the Personal Learning Portal API!"}

class TopicResponse(BaseModel):
    """Response model for a single topic."""
    id: int
    topic: str

@app.get("/topics/", response_model=list[TopicResponse])
async def get_all_topics(db: AsyncSession = Depends(get_db)):
    """
    Fetches all unique topics from the learning_topics table.
    """
    result = await db.execute(select(LearningTopic).order_by(LearningTopic.topic))
    topics = result.scalars().all()
    return topics