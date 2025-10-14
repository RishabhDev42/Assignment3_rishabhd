from google import genai
import json
import os
import dotenv
import asyncio
import re

dotenv.load_dotenv()


class AssessmentAgent:
    def __init__(self):
        google_api_key = os.getenv("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=google_api_key)
        self.model = 'gemini-2.5-flash'

    async def create_quiz(self, topic: str) -> dict | None:
        """
        Generates a 5-question multiple-choice quiz on a given topic.
        """
        # 1. Construct the prompt with strict JSON output instructions
        prompt = f"""
        Create a 5-question multiple-choice quiz about the following topic: "{topic}".

        **Instructions:**
        - The quiz must have exactly 5 questions.
        - Each question must have 4 options (a, b, c, d).
        - Indicate the correct answer for each question.
        - Your output MUST be a single, valid JSON object. Do not include any text before or after the JSON.

        **JSON Format:**
        {{
          "topic": "{topic}",
          "questions": [
            {{
              "question_text": "...",
              "options": {{ "a": "...", "b": "...", "c": "...", "d": "..." }},
              "correct_answer": "c",
              "explanation": "..."
            }}
          ]
        }}
        """

        # 2. Call Gemini and parse the JSON response
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                contents=prompt,
                model=self.model
            )
            print("Raw Gemini response:", response.text)
            response_text = response.text.strip()
            if response_text.startswith("```"):
                response_text = re.sub(r"^```[a-zA-Z]*\s*", "", response_text)
                response_text = re.sub(r"\s*```$", "", response_text)

            print("Cleaned Gemini response:", response_text)
            return json.loads(response_text)
        except (json.JSONDecodeError, Exception) as e:
            print(f"❌ Assessment Agent failed to generate or parse quiz JSON: {e}")
            return None