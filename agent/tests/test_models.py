"""Model resolver (design 2026-10-27, search filtered by watch model). The file names are the real staff manuals."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storegear.tools.models import Registry, display_name, resolve  # noqa: E402

FILES = [
    "Instinct_3_AMOLED_OM_ES-XM.pdf", "Instinct_3_Solar_OM_ES-XM.pdf", "Instinct_E_OM_ES-XM.pdf",
    "Instinct_Crossover_AMOLED_OM_ES-XM.pdf", "Venu_X1_OM_ES-XM.pdf", "Venu_4_OM_ES-XM.pdf", "vivoactive_6_OM_ES-XM.pdf",
    "Forerunner_70_OM_ES-XM.pdf", "Forerunner_170_Series_OM_ES-XM.pdf", "Forerunner_570_OM_ES-XM.pdf",
    "Forerunner_970_OM_ES-XM.pdf", "fenix_8_Series_OM_ES-XM.pdf",
    "Suunto_Ocean_UserGuide_ES.pdf", "Suunto_Run_UserGuide_ES.pdf", "Suunto_Vertical_2_UserGuide_ES.pdf",
    "Suunto_Race_2_UserGuide_ES.pdf", "Suunto_Race_2_UserGuide_EN.pdf",
    "Polar Ignite 2.pdf", "Polar Grit X2.pdf", "Polar Vantage M2.pdf", "Polar Vantage V2.pdf", "Polar Pacer Pro.pdf",
    "Polar Grit X Pro.pdf",
]
REG = Registry.from_files(FILES)


@pytest.mark.parametrize("file_name,expected", [
    ("Instinct_3_Solar_OM_ES-XM.pdf", "Garmin Instinct 3 Solar"),
    ("vivoactive_6_OM_ES-XM.pdf", "Garmin vivoactive 6"),
    ("fenix_8_Series_OM_ES-XM.pdf", "Garmin fenix 8"),
    ("Forerunner_170_Series_OM_ES-XM.pdf", "Garmin Forerunner 170"),
    ("Suunto_Race_2_UserGuide_EN.pdf", "Suunto Race 2"),
    ("Suunto_Ocean_UserGuide_ES.pdf", "Suunto Ocean"),
    ("Polar Grit X Pro.pdf", "Polar Grit X Pro"),
])
def test_display_name(file_name, expected):
    assert display_name(file_name) == expected


def test_registry_groups_languages_into_one_model():
    assert len(REG.models) == 22
    assert sorted(REG.models["Suunto Race 2"]) == ["Suunto_Race_2_UserGuide_EN.pdf", "Suunto_Race_2_UserGuide_ES.pdf"]


def models(text):
    return resolve(text, REG).models


@pytest.mark.parametrize("text,expected", [
    ("¿Cuánto dura la batería del Instinct 3 Solar?", ["Garmin Instinct 3 Solar"]),
    ("Instinct 3 AMOLED de 50 mm en modo solo GPS", ["Garmin Instinct 3 AMOLED"]),
    ("¿El Instinct E tiene linterna?", ["Garmin Instinct E"]),
    ("instinct crossover amoled: autonomía", ["Garmin Instinct Crossover AMOLED"]),
    ("Forerunner 970 frente al Forerunner 570", ["Garmin Forerunner 970", "Garmin Forerunner 570"]),
    ("¿Cuánto pesa el Forerunner 70?", ["Garmin Forerunner 70"]),
    ("Forerunner 170 series, ¿tiene NFC?", ["Garmin Forerunner 170"]),
    ("El fēnix 8 aguanta 100 m", ["Garmin fenix 8"]),
    ("¿el Garmin Fenix 8 Series tiene mapas?", ["Garmin fenix 8"]),
    ("vivoactive 6 y pagos", ["Garmin vivoactive 6"]),
    ("Venu 4 o Venu X1", ["Garmin Venu 4", "Garmin Venu X1"]),
    ("¿Se puede bucear con el Suunto Ocean?", ["Suunto Ocean"]),
    ("Suunto Race 2: brújula", ["Suunto Race 2"]),
    ("Instinct 3 AMOLED o el Polar Vantage M2", ["Garmin Instinct 3 AMOLED", "Polar Vantage M2"]),
    ("¿El Vantage V2 mide la potencia?", ["Polar Vantage V2"]),
    ("el pacer pro", ["Polar Pacer Pro"]),            # the only Pacer: a partial name is enough
    ("el grit x2 y el grit x pro", ["Polar Grit X2", "Polar Grit X Pro"]),
])
def test_named_models(text, expected):
    assert models(text) == expected


@pytest.mark.parametrize("text", [
    "¿Qué reloj me recomiendas para correr?",
    "Quiero un Garmin con buena batería",            # brand only: rule 7 (the agent asks), no filter
    "¿Qué velocidad vertical mide al subir?",        # ordinary words never name a Suunto
    "modo run con GPS",
    "",
])
def test_no_model_no_filter(text):
    r = resolve(text, REG)
    assert r.models == [] and r.ambiguous == [] and r.files is None


@pytest.mark.parametrize("text,candidates", [
    ("¿El Instinct 3 tiene linterna?", ["Garmin Instinct 3 AMOLED", "Garmin Instinct 3 Solar"]),
    ("batería del Forerunner", ["Garmin Forerunner 170", "Garmin Forerunner 570", "Garmin Forerunner 70", "Garmin Forerunner 970"]),
    ("el Venu tiene altavoz?", ["Garmin Venu 4", "Garmin Venu X1"]),
    ("el vantage", ["Polar Vantage M2", "Polar Vantage V2"]),
])
def test_partial_name_of_several_models_is_ambiguous(text, candidates):
    r = resolve(text, REG)
    assert r.models == [] and r.files is None
    assert r.ambiguous == [candidates]


def test_files_are_the_named_models_manuals():
    r = resolve("Suunto Race 2 vs Instinct 3 Solar", REG)
    assert sorted(r.files) == ["Instinct_3_Solar_OM_ES-XM.pdf", "Suunto_Race_2_UserGuide_EN.pdf", "Suunto_Race_2_UserGuide_ES.pdf"]


def test_polar_adds_the_common_manual():
    assert "Polar · información común" in resolve("Polar Ignite 2 nadar", REG).files
    assert "Polar · información común" not in resolve("Venu 4 nadar", REG).files


def test_a_full_name_wins_over_an_ambiguous_mention():
    r = resolve("Instinct 3 Solar, ¿y el Instinct 3 en general?", REG)
    assert r.models == ["Garmin Instinct 3 Solar"] and r.ambiguous == []


def test_a_model_missing_from_the_catalog_is_never_taken_for_a_similar_one():
    # before the new manuals were ingested, "Instinct 3 Solar" partly matched the only Instinct 3 (the AMOLED)
    reg = Registry.from_files([f for f in FILES if "Solar" not in f])
    r = resolve("bateria del Instinct 3 Solar", reg)
    assert r.models == [] and r.files is None
