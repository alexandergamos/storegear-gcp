"""SMO-15 · Deploy (or update) the StoreGear agent on Agent Runtime (ADR-008).

    uv run python infra/deploy_agent_runtime.py            # first deploy: creates the agent, prints its resource name
    uv run python infra/deploy_agent_runtime.py --update   # later deploys: updates the same agent in place

The resource name is saved in infra/agent_runtime.json (committed; it is an identifier, not a secret).
"""
import argparse
import json
import os
import sys
from pathlib import Path

import vertexai  # deprecated name; agentplatform.Client renames agent_engines -> runtimes (migrate later)
from vertexai import agent_engines  # AdkApp still lives here in aiplatform 2.5

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "storegear-prod-ag26"
LOCATION = "eu"  # EU multi-region: serves gemini-3.8-flash + gemini-embedding-2 (ADR-008)
STAGING = "gs://storegear-prod-ag26-agent-staging"
SA = f"sg-agent@{PROJECT}.iam.gserviceaccount.com"
STATE = ROOT / "infra" / "agent_runtime.json"

REQUIREMENTS = [
    "google-cloud-aiplatform[agent_engines,adk]>=1.112",
    "google-adk>=2.0",
    "cloud-sql-python-connector[pg8000]>=1.23.0",
    "sqlalchemy>=2.0",
    "pydantic>=2.14",       # needed by the runtime to unpickle the app (SDK warns if missing)
    "cloudpickle>=3.1",
]
ENV = {
    "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
    "STOREGEAR_MODEL": "gemini-3.8-flash",
    "STOREGEAR_THINKING": "low",
    "STOREGEAR_MODEL_TIMEOUT_MS": "15000",
    "STOREGEAR_EMBED_LOCATION": "eu",
    "STOREGEAR_DB_USER": f"sg-agent@{PROJECT}.iam",  # runtime credentials don't expose the SA email until refreshed
}


def main(update: bool) -> None:
    os.chdir(ROOT / "agent")          # so `storegear` is importable and packaged by its folder name
    sys.path.insert(0, str(ROOT / "agent"))
    from storegear.agent import root_agent

    # AdkApp captures project/location from vertexai.init() and the runtime uses them for Sessions and model calls.
    # Without this it silently defaults to us-central1 ("The ReasoningEngine does not exist" on first session).
    vertexai.init(project=PROJECT, location=LOCATION, staging_bucket=STAGING)
    client = vertexai.Client(project=PROJECT, location=LOCATION)
    app = agent_engines.AdkApp(agent=root_agent)
    config = {
        "display_name": "storegear-agent",
        "description": "StoreGear Assistant: smartwatch manuals + live price/stock (ADK, Gemini 3.8 Flash)",
        "requirements": REQUIREMENTS,
        "extra_packages": ["storegear"],
        "staging_bucket": STAGING,
        "service_account": SA,
        "env_vars": ENV,
        "min_instances": 0,
        "max_instances": 2,
        "resource_limits": {"cpu": "1", "memory": "2Gi"},
    }
    if update:
        name = json.loads(STATE.read_text())["resource_name"]
        remote = client.agent_engines.update(name=name, agent=app, config=config)
    else:
        remote = client.agent_engines.create(agent=app, config=config)
    name = remote.api_resource.name
    STATE.write_text(json.dumps({"resource_name": name, "location": LOCATION}, indent=2))
    print("deployed:", name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    main(ap.parse_args().update)
