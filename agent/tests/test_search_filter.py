"""Search filtered by watch model: the SQL filter, the catalog's model list and the agent's shared search step."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storegear import agent  # noqa: E402
from storegear.tools import search  # noqa: E402
from storegear.tools.models import Registry  # noqa: E402

FILES = ["Instinct_3_AMOLED_OM_ES-XM.pdf", "Instinct_3_Solar_OM_ES-XM.pdf", "Polar Ignite 2.pdf", "Venu_X1_OM_ES-XM.pdf"]


class FakeConn:
    def __init__(self, rows, seen):
        self.rows, self.seen = rows, seen

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.seen.append((str(sql), params))
        rows = self.rows

        class R:
            def mappings(self):
                return self

            def all(self):
                return rows

            def fetchall(self):
                return rows
        return R()


class FakeEngine:
    def __init__(self, rows=()):
        self.rows, self.seen = list(rows), []

    def connect(self):
        return FakeConn(self.rows, self.seen)


def test_hybrid_search_sends_the_manuals_filter(monkeypatch):
    eng = FakeEngine()
    monkeypatch.setattr(search, "engine", lambda: eng)
    monkeypatch.setattr(search, "embed_query", lambda q: [0.0])
    search.hybrid_search("bateria Instinct 3 Solar", files=["Instinct_3_Solar_OM_ES-XM.pdf"])
    sql, params = eng.seen[-1]
    assert params["files"] == ["Instinct_3_Solar_OM_ES-XM.pdf"]
    assert "c.file_name = ANY(" in sql
    # manager-only documents (no model name) stay searchable for a manager when a model is named
    assert "c.access_level = 'manager'" in sql.split("allowed AS")[1].split("dense AS")[0]


def test_hybrid_search_without_models_has_no_filter(monkeypatch):
    eng = FakeEngine()
    monkeypatch.setattr(search, "engine", lambda: eng)
    monkeypatch.setattr(search, "embed_query", lambda q: [0.0])
    search.hybrid_search("que reloj para correr")
    assert eng.seen[-1][1]["files"] is None


def test_registry_comes_from_the_staff_manuals_and_is_cached(monkeypatch):
    eng = FakeEngine(rows=[(f,) for f in FILES])
    monkeypatch.setattr(search, "engine", lambda: eng)
    monkeypatch.setattr(search, "_registry", None)
    reg = search.catalog_registry()
    assert "Garmin Instinct 3 Solar" in reg.models
    sql = " ".join(eng.seen[-1][0].split())
    assert "access_level = 'staff'" in sql and "file_id <> 'polar-common'" in sql
    search.catalog_registry()
    assert len(eng.seen) == 1


def test_search_step_filters_by_the_named_model(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "catalog_registry", lambda: Registry.from_files(FILES))
    monkeypatch.setattr(agent, "hybrid_search", lambda q, role="staff", files=None: calls.append(files) or [])
    agent.search_step("¿Cuánto dura la batería del Instinct 3 Solar?", "staff")
    assert calls == [["Instinct_3_Solar_OM_ES-XM.pdf"]]


def test_search_step_asks_instead_of_searching_when_ambiguous(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "catalog_registry", lambda: Registry.from_files(FILES))
    monkeypatch.setattr(agent, "hybrid_search", lambda *a, **k: calls.append(1) or [])
    text = agent.search_step("¿El Instinct 3 tiene linterna?", "staff")
    assert calls == []
    assert "Garmin Instinct 3 AMOLED" in text and "Garmin Instinct 3 Solar" in text
    assert "pregunta" in text.lower()


def test_search_step_without_a_model_searches_everything(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "catalog_registry", lambda: Registry.from_files(FILES))
    monkeypatch.setattr(agent, "hybrid_search", lambda q, role="staff", files=None: calls.append(files) or [])
    agent.search_step("¿Qué reloj me recomiendas para nadar?", "staff")
    assert calls == [None]


def test_model_list_follows_the_catalog(monkeypatch):
    monkeypatch.setattr(agent, "catalog_registry", lambda: Registry.from_files(FILES))
    block = agent.model_list_block()
    assert "MODELOS EN EL CATALOGO" in block
    assert "Garmin: Instinct 3 AMOLED, Instinct 3 Solar, Venu X1" in block
    assert "Polar: Ignite 2" in block


def test_the_prompt_no_longer_hard_codes_the_models():
    assert "- Garmin: Instinct 3 AMOLED, Venu X1" not in agent.PROMPT
