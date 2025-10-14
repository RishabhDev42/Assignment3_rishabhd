import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, TEXT, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from backend.db.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship



class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sender: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(TEXT, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class LearningTopic(Base):
    __tablename__ = "learning_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    topic: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    questions: Mapped[list["QuizQuestion"]] = relationship(back_populates="quiz")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quizzes.id"))
    question_text: Mapped[str] = mapped_column(TEXT)
    options: Mapped[dict] = mapped_column(JSONB)
    correct_answer: Mapped[str] = mapped_column(String(255))
    explanation: Mapped[str] = mapped_column(TEXT, nullable=True)  # To store the explanation

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")