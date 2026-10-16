"""SMO-9 hello world: the smallest ADK agent, running on Agent Platform models with your Google login.

What to notice:
- `root_agent` is the only thing ADK requires. `adk web` / `adk run` look for it by name.
- A tool is a plain Python function. ADK reads its name, type hints and docstring and turns them into the
  tool description the model sees, so the docstring is part of the prompt.
- No API key anywhere: `.env` says "use Agent Platform" (GOOGLE_GENAI_USE_VERTEXAI) and the SDK finds your
  credentials through Application Default Credentials (`gcloud auth application-default login`).
"""
import os

from google.adk.agents import Agent


def get_store_hours(city: str) -> dict:
    """Returns the opening hours of the StoreGear shop in a city.

    Args:
        city: Name of the city, for example "Barcelona".
    """
    # Mock data: SMO-13 replaces this with the real price/stock tool.
    hours = {"barcelona": "10:00-21:00", "madrid": "10:00-22:00"}
    found = hours.get(city.strip().lower())
    if not found:
        return {"status": "not_found", "city": city}
    return {"status": "success", "city": city, "hours": found}


root_agent = Agent(
    name="hello_agent",
    model=os.getenv("STOREGEAR_MODEL", "gemini-3.8-flash"),
    description="Smoke test: answers opening-hours questions with one tool.",
    instruction=(
        "You are a shop assistant. When asked about opening hours, call get_store_hours. "
        "If the tool returns not_found, say you don't have that city. Answer in the user's language."
    ),
    tools=[get_store_hours],
)
