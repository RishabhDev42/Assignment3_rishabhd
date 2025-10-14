from google import genai
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.db.models import LearningTopic
from backend.db.models import ConversationHistory
import os
import dotenv

dotenv.load_dotenv()


class LearningNavigatorAgent:
    def __init__(self):
        google_api_key = os.getenv("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=google_api_key)
        self.model = 'gemini-2.5-flash'

    async def suggest_next_steps(self, db: AsyncSession) -> list[str]:
        """
        Provides four targeted prompts for the user to explore next.
        """
        # 1. Get all learned topics
        stmt = (
            select(LearningTopic)
            .order_by(LearningTopic.created_at.desc())
            .limit(3)
        )
        result = await db.execute(stmt)
        topics = result.scalars().all()
        learned_topics = ", ".join([t.topic for t in topics])

        # 2. Get last up to 5 user messages
        user_stmt = (
            select(ConversationHistory)
            .where(ConversationHistory.sender == "user")
            .order_by(ConversationHistory.timestamp.desc())
            .limit(5)
        )
        user_result = await db.execute(user_stmt)
        user_messages = user_result.scalars().all()
        recent_user_text = "\n".join([msg.content for msg in reversed(user_messages)])

        # 2. Construct the prompt
        prompt = f"""
        You are a learning navigator. Based on the user's recent messages and the topics already covered, suggest four engaging and logical next-step questions to deepen the user's understanding.

        **Recent User Messages:**
        {recent_user_text}
        
        **Topics Already Covered:**
        {learned_topics}

        **Instructions:**
        - Provide exactly four distinct suggestions.
        - Frame them as questions the user could ask.
        - Do not number them. Use a hyphen (-) for each suggestion.
        """

        # 3. Call Gemini and parse the response
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        suggestions = [line.replace('-', '').strip() for line in response.text.strip().split('\n')]
        return suggestions[:4]  # Ensure only 4 are returned