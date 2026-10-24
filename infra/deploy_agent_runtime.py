"""SMO-15 · Deploy (or update) the StoreGear agent on Agent Runtime (ADR-008).

    uv run python infra/deploy_agent_runtime.py            # first deploy: creates the agent, prints its resource name
    uv run python infra/deploy_agent_runtime.py --update   # later deploys: updates the same agent in place

The resource name is saved in infra/agent_runtime.json (committed; it is an identifier, not a secret).
"""
import argparse
import json
import os
import subprocess
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
    "GOOGLE_CLOUD_LOCATION": LOCATION,  # model calls (GOOGLE_CLOUD_AGENT_ENGINE_* names are reserved by the runtime)
    "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
    "STOREGEAR_MODEL": "gemini-3.8-flash",
    "STOREGEAR_THINKING": "low",
    "STOREGEAR_MODEL_TIMEOUT_MS": "15000",
    "STOREGEAR_EMBED_LOCATION": "eu",
    "STOREGEAR_RETURN_N": "7",   # sections handed to the model; 5 -> 7 on 2026-10-21 (Q10 ranks 7th), see SMO-33 reranker
    "STOREGEAR_SHEETS_SA": SA,  # self-impersonation for a spreadsheets-scoped token (metadata tokens lack it)
    "STOREGEAR_PROJECT_ID": PROJECT,  # the runtime's GOOGLE_CLOUD_PROJECT is the project number
    "STOREGEAR_DB_USER": f"sg-agent@{PROJECT}.iam",  # runtime credentials don't expose the SA email until refreshed
    # SMO-25 (ADR-019): traces of model and tool calls to Cloud Trace (the SDK's supported switch; enable_tracing is
    # deprecated). Prompt and answer text are NOT captured: content capture stays explicitly off.
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
    "STOREGEAR_RELEASE": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                        cwd=ROOT).stdout.strip() or "dev",   # the commit this agent was deployed from
}


def eu_session_service():
    """Managed Sessions pinned to the eu multi-region endpoint (aiplatform.eu.rep.googleapis.com).
    Inside the runtime the default builder uses a reserved location variable that doesn't resolve to 'eu'
    (sessions then 404 with "The ReasoningEngine does not exist"); pinning it explicitly works."""
    import os
    from google.adk.sessions import VertexAiSessionService
    return VertexAiSessionService(project="storegear-prod-ag26", location="eu",
                                  agent_engine_id=os.environ["GOOGLE_CLOUD_AGENT_ENGINE_ID"])


def main(update: bool) -> None:
    os.chdir(ROOT / "agent")          # so `storegear` is importable and packaged by its folder name
    sys.path.insert(0, str(ROOT / "agent"))
    from storegear.agent import root_agent

    client = vertexai.Client(project=PROJECT, location=LOCATION)
    app = agent_engines.AdkApp(agent=root_agent, session_service_builder=eu_session_service)
    # The template takes project/location from vertexai.init() and uses them in the runtime for Sessions and models.
    # vertexai.init(location="eu") is rejected by this SDK's region check, and the runtime reserves the
    # GOOGLE_CLOUD_AGENT_ENGINE_* env vars, so set the captured values directly (otherwise: us-central1 -> 404).
    app._tmpl_attrs["project"] = PROJECT
    app._tmpl_attrs["location"] = LOCATION
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
