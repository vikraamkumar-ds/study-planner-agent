"""
main.py
-------
Run the full Study Planner capstone end-to-end.

Usage:
    export GOOGLE_API_KEY="your-gemini-api-key"     # get one free at aistudio.google.com
    python main.py "Learn enough SQL for a job interview" 5

Args:
    goal      : the learning goal (string)
    days      : deadline in days (int)
"""

import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

from agent import root_agent


async def run(goal: str, days: int, user_id: str = "student_1"):
    runner = InMemoryRunner(agent=root_agent, app_name="study_planner_app")

    session = await runner.session_service.create_session(
        app_name="study_planner_app", user_id=user_id
    )

    prompt = f"My goal is: {goal}. My deadline is {days} days from today."
    user_message = genai_types.Content(
        role="user", parts=[genai_types.Part(text=prompt)]
    )

    print(f"\n>>> USER REQUEST: {prompt}\n" + "-" * 60)

    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=user_message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    speaker = event.author or "agent"
                    print(f"\n[{speaker}]\n{part.text}")
                if getattr(part, "function_call", None):
                    print(f"\n[{event.author}] -> calling tool: {part.function_call.name}({part.function_call.args})")
                if getattr(part, "function_response", None):
                    print(f"\n[{event.author}] <- tool result: {part.function_response.response}")


if __name__ == "__main__":
    goal = sys.argv[1] if len(sys.argv) > 1 else "Learn enough Python for a data analyst internship"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    asyncio.run(run(goal, days))
