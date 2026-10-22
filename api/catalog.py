"""Display names for the manuals, for the web demo's empty state ("Modelos en el catálogo")."""
from typing import Callable

SUFFIXES = ("_OM_ES-XM", "_UserGuide_ES")
GARMIN = ("Instinct", "Venu", "Fenix", "Forerunner", "Edge")


def display_name(file_name: str) -> str:
    name = file_name.rsplit(".", 1)[0]
    for s in SUFFIXES:
        name = name.removesuffix(s)
    name = name.replace("_", " ").strip()
    if name.startswith(GARMIN):
        name = f"Garmin {name}"
    if file_name.startswith("Suunto_") and not name.startswith("Suunto"):
        name = f"Suunto {name}"
    return name


def list_models(fetch_file_names: Callable[[], list[str]]) -> list[str]:
    return sorted({display_name(f) for f in fetch_file_names() if f})
