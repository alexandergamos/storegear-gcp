"""Which catalog models a text names (design 2026-10-27: search filtered by watch model).

The list of models comes from the catalog's own manual names, so a manual added in Drive is a model here with no code
or prompt change. Matching is deterministic, never an LLM guess:
- names match as whole words, accents and case ignored ("fēnix" = "fenix"); the longest name wins, so
  "Instinct 3 Solar" never also counts as "Instinct 3 AMOLED" and "Forerunner 970" never as "Forerunner 70";
- a partial name that fits several models is ambiguous ("el Instinct 3"): the agent asks which one instead of
  searching. One that fits a single model names nothing: "Instinct 3 Solar" must never become the only Instinct 3 in
  the catalog when the Solar isn't there, so the search runs unfiltered, as before;
- a brand alone ("un Garmin") names nothing: rule 7 of the prompt already makes the agent ask.
"""
import re
import unicodedata
from dataclasses import dataclass, field

SUFFIXES = ("_OM_ES-XM", "_UserGuide_ES", "_UserGuide_EN")
GARMIN = ("instinct", "venu", "fenix", "forerunner", "edge", "vivoactive")
BRANDS = ("garmin", "polar", "suunto")
# A name that starts with an everyday word ("velocidad vertical", "modo run") only counts with its brand.
COMMON_WORDS = {"run", "race", "vertical", "ocean", "pro", "series"}
POLAR_COMMON = "Polar · información común"   # the pseudo-manual of sections shared by Polar models (ingestion)


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.findall(r"[a-z0-9]+", text)


def display_name(file_name: str) -> str:
    name = file_name.rsplit(".", 1)[0]
    for s in SUFFIXES:
        name = name.removesuffix(s)
    name = name.replace("_", " ").strip().removesuffix(" Series")
    if name.lower().startswith(GARMIN):
        name = f"Garmin {name}"
    if file_name.startswith("Suunto_") and not name.startswith("Suunto"):
        name = f"Suunto {name}"
    return name


@dataclass
class Registry:
    models: dict[str, list[str]]                       # display name -> its manuals (one model can have two languages)
    keys: list[tuple[tuple[str, ...], str]] = field(default_factory=list)   # word sequence -> display name

    @classmethod
    def from_files(cls, file_names) -> "Registry":
        models: dict[str, list[str]] = {}
        for f in file_names:
            if f and f != POLAR_COMMON:
                models.setdefault(display_name(f), []).append(f)
        keys = []
        for name in models:
            full = tuple(words(name))
            keys.append((full, name))
            bare = full[1:] if full[0] in BRANDS else full
            if bare != full and len(bare) > 1 and bare[0] not in COMMON_WORDS:
                keys.append((bare, name))
        return cls(models, keys)


@dataclass
class Resolution:
    models: list[str]                     # named models, in the order they are mentioned
    ambiguous: list[list[str]]            # each partial mention that fits several models: its candidates
    files: list[str] | None               # manuals to search; None = no filter


def _find(seq: tuple[str, ...], toks: list[str]):
    n = len(seq)
    return [i for i in range(len(toks) - n + 1) if tuple(toks[i:i + n]) == seq]


def resolve(text: str, reg: Registry) -> Resolution:
    toks = words(text)
    hits = [(i, i + len(k), name) for k, name in reg.keys for i in _find(k, toks)]
    hits.sort(key=lambda h: (-(h[1] - h[0]), h[0]))
    taken, named = set(), []
    for start, end, name in hits:                      # longest first; a shorter name inside a longer one is skipped
        if not taken & set(range(start, end)):
            taken |= set(range(start, end))
            named.append((start, name))

    ambiguous = []
    i = 0
    while i < len(toks):
        if i in taken or toks[i] in COMMON_WORDS or toks[i] in BRANDS and (i + 1 >= len(toks) or i + 1 in taken):
            i += 1
            continue
        best, best_len = None, 0                       # the longest run of words that starts some model's name
        for j in range(i + 1, len(toks) + 1):
            if j - 1 in taken:
                break
            seq = tuple(toks[i:j])
            fits = sorted({name for k, name in reg.keys if k[:len(seq)] == seq})
            if not fits:
                break
            if seq not in BRANDS_SEQ:
                best, best_len = fits, j - i
        if best and len(best) > 1:
            ambiguous.append(best)
        i += max(best_len, 1)

    order: list[str] = []
    for _, name in sorted(named):
        if name not in order:
            order.append(name)
    if order:
        files = [f for name in order for f in reg.models[name]]
        if any(name.startswith("Polar") for name in order):
            files.append(POLAR_COMMON)
        return Resolution(order, [], files)
    return Resolution([], ambiguous, None)


BRANDS_SEQ = {(b,) for b in BRANDS}
