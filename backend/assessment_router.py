from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import uuid

from sqlalchemy.future import select

from backend.db.deps import get_db
from backend.agents.assessment_agent import AssessmentAgent
from backend.db.models import Quiz, QuizQuestion


# --- Pydantic Models for the API ---
class StartQuizRequest(BaseModel):
    topic: str


class QuestionResponse(BaseModel):
    question_id: uuid.UUID
    question_text: str
    options: dict

class AnswerRequest(BaseModel):
    question_id: uuid.UUID
    answer: str  # e.g., "a"


class AnswerResponse(BaseModel):
    is_correct: bool
    explanation: str
    correct_answer: str
    next_question: QuestionResponse | None = None  # Null if quiz is over

class QuestionModel(BaseModel):
    question_text: str
    options: dict
    correct_answer: str
    explanation: str

class QuizDataModel(BaseModel):
    topic: str
    questions: list[QuestionModel]

class StartQuizResponse(BaseModel):
    quiz_id: uuid.UUID
    quiz_data: QuizDataModel


# --- Router Setup ---
router = APIRouter(prefix="/assessment", tags=["Assessment"])
assessment_agent = AssessmentAgent()


@router.post("/start", response_model=StartQuizResponse)
async def start_quiz(request: StartQuizRequest, db: AsyncSession = Depends(get_db)):
    """
    Starts a new quiz on a given topic.
    """
    # 1. Generate quiz content using the Assessment Agent
    quiz_data = await assessment_agent.create_quiz(request.topic)
    if not quiz_data or not quiz_data.get("questions"):
        raise HTTPException(status_code=500, detail="Failed to generate quiz content.")

    # 2. Save the new quiz and its questions to the database
    new_quiz = Quiz(topic=request.topic)
    db.add(new_quiz)
    await db.flush()  # Flush to get the new_quiz.id

    questions_to_add = []
    for q_data in quiz_data["questions"]:
        questions_to_add.append(
            QuizQuestion(
                quiz_id=new_quiz.id,
                question_text=q_data["question_text"],
                options=q_data["options"],
                correct_answer=q_data["correct_answer"],
                explanation=q_data.get("explanation", "No explanation provided.")
                # Add explanation generation to your agent
            )
        )
    db.add_all(questions_to_add)
    await db.commit()

    # Assemble the full quiz object to send to the frontend
    quiz_data_model = QuizDataModel(
        topic=new_quiz.topic,
        questions=[
            QuestionModel(
                question_text=q.question_text,
                options=q.options,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
            )
            for q in questions_to_add
        ]
    )

    # Return the full quiz object
    return StartQuizResponse(
        quiz_id=new_quiz.id,
        quiz_data=quiz_data_model
    )


@router.post("/answer", response_model=AnswerResponse)
async def submit_answer(request: AnswerRequest, db: AsyncSession = Depends(get_db)):
    """
    Submits an answer to a question and gets the next one.
    """
    # 1. Find the question being answered
    question = await db.get(QuizQuestion, request.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found.")

    # 2. Check if the answer is correct
    is_correct = (request.answer == question.correct_answer)

    # (Here you would save the user's attempt/answer to the database)

    # 3. Find the next question in the same quiz
    # This is a simplified way to get the next question
    all_questions = await db.execute(
        select(QuizQuestion).where(QuizQuestion.quiz_id == question.quiz_id).order_by(QuizQuestion.id)
    )
    question_list = all_questions.scalars().all()

    current_index = -1
    for i, q in enumerate(question_list):
        if q.id == request.question_id:
            current_index = i
            break

    next_question_obj = None
    if current_index != -1 and current_index + 1 < len(question_list):
        next_q_db = question_list[current_index + 1]
        next_question_obj = QuestionResponse(
            question_id=next_q_db.id,
            question_text=next_q_db.question_text,
            options=next_q_db.options
        )

    return AnswerResponse(
        is_correct=is_correct,
        correct_answer=question.correct_answer,
        explanation=question.explanation,
        next_question=next_question_obj
    )