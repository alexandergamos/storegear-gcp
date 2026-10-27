import pytest

import catalog
import main

STAFF_FILES = {
    "Instinct_3_AMOLED_OM_ES-XM.pdf": "Garmin Instinct 3 AMOLED",
    "Venu_X1_OM_ES-XM.pdf": "Garmin Venu X1",
    "Suunto_Ocean_UserGuide_ES.pdf": "Suunto Ocean",
    "Polar Ignite 2.pdf": "Polar Ignite 2",
    "Polar Grit X2.pdf": "Polar Grit X2",
    "Polar Vantage M2.pdf": "Polar Vantage M2",
    "Polar Vantage V2.pdf": "Polar Vantage V2",
    "Polar Pacer Pro.pdf": "Polar Pacer Pro",
    "Polar Grit X Pro.pdf": "Polar Grit X Pro",
}


NEW_FILES = {   # added 2026-10-27; the agent's resolver (agent/storegear/tools/models.py) names them the same way
    "Instinct_3_Solar_OM_ES-XM.pdf": "Garmin Instinct 3 Solar",
    "vivoactive_6_OM_ES-XM.pdf": "Garmin vivoactive 6",
    "fenix_8_Series_OM_ES-XM.pdf": "Garmin fenix 8",
    "Forerunner_170_Series_OM_ES-XM.pdf": "Garmin Forerunner 170",
    "Suunto_Race_2_UserGuide_EN.pdf": "Suunto Race 2",
    "Suunto_Race_2_UserGuide_ES.pdf": "Suunto Race 2",
}


@pytest.mark.parametrize("file_name,expected", [*STAFF_FILES.items(), *NEW_FILES.items(), ("Foo_Bar_OM_ES-XM.pdf", "Foo Bar")])
def test_display_name(file_name, expected):
    assert catalog.display_name(file_name) == expected


def test_list_models_dedups_and_sorts():
    files = ["Polar Ignite 2.pdf", "Venu_X1_OM_ES-XM.pdf", "Polar Ignite 2.pdf"]
    assert catalog.list_models(lambda: files) == ["Garmin Venu X1", "Polar Ignite 2"]


def test_models_endpoint_is_public_and_staff_only(client, monkeypatch):
    # the fake fetch returns what the staff-only SQL returns: a manager file never comes back from it
    monkeypatch.setattr(main, "staff_file_names", lambda: list(STAFF_FILES))
    monkeypatch.setattr(main, "_models_cache", None)
    r = client.get("/catalog/models")
    assert r.status_code == 200
    assert r.json() == {"models": sorted(STAFF_FILES.values())}


def test_staff_file_names_sql_filters_staff_and_common(monkeypatch):
    seen = {}

    class Cur:
        def execute(self, sql, *a):
            seen["sql"] = " ".join(sql.split())

        def fetchall(self):
            return [("Polar Ignite 2.pdf",)]

    class Conn:
        def cursor(self):
            return Cur()

        def close(self):
            seen["closed"] = True

    monkeypatch.setattr(main, "db", Conn)
    assert main.staff_file_names() == ["Polar Ignite 2.pdf"]
    assert seen["sql"] == "SELECT DISTINCT file_name FROM catalog_chunks WHERE access_level = 'staff' AND file_id <> 'polar-common'"
    assert seen["closed"]


def test_models_are_cached(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "staff_file_names", lambda: calls.append(1) or ["Polar Ignite 2.pdf"])
    monkeypatch.setattr(main, "_models_cache", None)
    client.get("/catalog/models")
    client.get("/catalog/models")
    assert len(calls) == 1


def test_sg_api_reads_only_the_columns_it_needs():
    # sg-api is internet-facing: it may read file names and access levels, never chunk text (manager manuals included)
    import pathlib
    sql = (pathlib.Path(__file__).parents[2] / "infra" / "sql" / "009_web_demo.sql").read_text(encoding="utf-8")
    grants = [line for line in sql.splitlines() if line.startswith("GRANT") and "catalog_chunks" in line]
    assert grants == ['GRANT SELECT (file_name, access_level, file_id) ON catalog_chunks TO "sg-api@storegear-prod-ag26.iam";']
