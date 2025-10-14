from google import genai
from google.genai import types
from pymilvus import Collection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.db.models import ConversationHistory, LearningTopic
from langchain.embeddings.huggingface import HuggingFaceEmbeddings
import os
import dotenv

dotenv.load_dotenv()


class TrainerAgent:
    def __init__(self, milvus_collection: Collection, embedding_model="sentence-transformers/all-mpnet-base-v2"):
        google_api_key = os.getenv("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=google_api_key)
        self.grounding_tool = types.Tool(google_search=types.GoogleSearch())
        self.model = "gemini-2.5-pro"
        self.config = types.GenerateContentConfig(tools=[self.grounding_tool])
        self.milvus_collection = milvus_collection
        self.embedding_model = HuggingFaceEmbeddings(model_name=embedding_model)

    def add_citations(self, response):
        text = response.text
        supports = response.candidates[0].grounding_metadata.grounding_supports
        chunks = response.candidates[0].grounding_metadata.grounding_chunks

        # Sort supports by end_index in descending order to avoid shifting issues when inserting.
        sorted_supports = sorted(supports, key=lambda s: s.segment.end_index, reverse=True)

        for support in sorted_supports:
            end_index = support.segment.end_index
            if support.grounding_chunk_indices:
                # Create citation string like [1](link1)[2](link2)
                citation_links = []
                for i in support.grounding_chunk_indices:
                    if i < len(chunks):
                        uri = chunks[i].web.uri
                        citation_links.append(f"[{i + 1}]({uri})")

                citation_string = ", ".join(citation_links)
                text = text[:end_index] + citation_string + text[end_index:]

        return text

    async def answer_query(self, db: AsyncSession, user_query: str) -> str:
        """
        Answers a user's query using RAG and Google Search grounding.
        """
        # 1. Retrieve context from Milvus
        query_embedding = self.embedding_model.embed_query(user_query)
        search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
        results = self.milvus_collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=5,
            output_fields=["passage"]
        )
        retrieved_context = "\n".join([res.entity.get('passage') for res in results[0]])

        # 2. Retrieve conversation history (short-term memory)
        stmt = select(ConversationHistory).order_by(ConversationHistory.timestamp.desc()).limit(10)
        result = await db.execute(stmt)
        history = result.scalars().all()
        conversation_history = "\n".join([f"{msg.sender}: {msg.content}" for msg in reversed(history)])

        # 3. Retrieve learned topics (long-term memory)
        stmt_topics = select(LearningTopic)
        result_topics = await db.execute(stmt_topics)
        topics = result_topics.scalars().all()
        long_term_memory = "\n".join([f"- {topic.topic}: {topic.description}" for topic in topics])

        # 4. Construct the prompt for Gemini
        prompt = f"""
        You are a personalized learning assistant. Your goal is to provide a clear and comprehensive answer to the user's question.

        **User's Question:**
        {user_query}

        **Here is some context retrieved from the learning materials:**
        <retrieved_context>
        {retrieved_context}
        </retrieved_context>

        **Here is our recent conversation history:**
        <conversation_history>
        {conversation_history}
        </conversation_history>

        **Here are the topics we have already covered (long-term memory):**
        <long_term_memory>
        {long_term_memory}
        </long_term_memory>

        **Instructions:**
        1. Synthesize the information from the retrieved context, conversation history, and long-term memory to formulate your answer.
        2. If the provided context is insufficient or the question requires very recent information, use your built-in Google Search tool to find the most up-to-date facts.
        3. Provide a direct and helpful answer. Cite the source of your information if it comes from an external search.
        """

        # 5. Call the Gemini API
        response = self.client.models.generate_content(model=self.model,
            contents=prompt,
            config=self.config)
        text_with_citations = self.add_citations(response)
        return text_with_citations