from google import genai
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert
from backend.db.models import ConversationHistory, LearningTopic
import os
import dotenv

dotenv.load_dotenv()


class SummaryAgent:
    def __init__(self):
        google_api_key = os.getenv("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=google_api_key)
        self.model = 'gemini-2.5-flash'

    async def summarize_conversation(self, db: AsyncSession):
        """
        Analyzes recent conversation and updates the learning_topics table.
        """
        # 1. Get recent conversation
        stmt = select(ConversationHistory).order_by(ConversationHistory.timestamp.desc()).limit(10)
        result = await db.execute(stmt)
        history = result.scalars().all()
        conversation_text = "\n".join([f"{msg.sender}: {msg.content}" for msg in reversed(history)])

        # 2. Construct the prompt
        prompt = f"""
        Analyze the following conversation and identify the primary learning topic discussed.
        Provide a concise, one-sentence description of the topic.

        Your output MUST be in the following format:
        Topic: [The main topic]
        Description: [A one-sentence summary of what was learned]

        **Conversation:**
        {conversation_text}
        """

        # 3. Call the Gemini API
        response = self.client.models.generate_content(model=self.model, contents=prompt)

        # 4. Parse the response and upsert into the database
        try:
            lines = response.text.strip().split('\n')
            topic = lines[0].replace('Topic: ', '').strip()
            description = lines[1].replace('Description: ', '').strip()

            if topic and description:
                # Use "upsert" to insert a new topic or update the description if it already exists
                stmt = insert(LearningTopic).values(
                    topic=topic,
                    description=description
                ).on_conflict_do_update(
                    index_elements=['topic'],
                    set_=dict(description=description)
                )
                await db.execute(stmt)
                await db.commit()
                print(f"✅ Summary Agent updated topic: {topic}")
        except Exception as e:
            print(f"❌ Summary Agent failed to parse or update: {e}")