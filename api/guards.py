"""SMO-23 · Guardrails for sg-api (ADR-015). Deterministic checks first; Model Armor and the topic check only where
a rule can't decide.

    mask_pii(text)          -> (masked text, kinds found)       regex + check digits; runs on input AND output
    armor(text, response)   -> list of matched filters          Model Armor template sg-guard (eu)
    on_topic(text)          -> bool                             Gemini 3.8 Flash (eu), typed JSON; unsure = on topic
    leak(answer)            -> str | None                       tool names, internal ids, verbatim prompt fragments
    strip_links(answer)     -> (answer, removed)                URLs outside the brands' domains are removed
"""
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

import google.auth
from google import genai
from google.auth.transport.requests import AuthorizedSession
from google.genai import types

PROJECT = os.getenv("STOREGEAR_PROJECT_ID", "storegear-prod-ag26")
ARMOR = os.getenv("STOREGEAR_ARMOR_GUARD", f"projects/{PROJECT}/locations/eu/templates/sg-guard")
ARMOR_URL = f"https://modelarmor.eu.rep.googleapis.com/v1/{ARMOR}"
MODEL = os.getenv("STOREGEAR_GUARD_MODEL", "gemini-3.8-flash")
ALLOWED_DOMAINS = {"garmin.com", "polar.com", "suunto.com", "support.garmin.com", "support.polar.com"}

# ------------------------------------------------------------------ 1 · PII (deterministic)
DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PHONE = re.compile(r"(?<![\w+])(?:\+34[\s.-]?|0034[\s.-]?)?[6789]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}(?!\d)")
DNI_NIE = re.compile(r"\b(?:([XYZ])[\s.-]?)?(\d{7,8})[\s.-]?([A-Z])\b", re.I)
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[\s]?[A-Z0-9]{4}){3,7}(?:[\s]?[A-Z0-9]{1,4})?\b")
CARD = re.compile(r"\b(?:\d[\s-]?){13,19}\b")


def _dni_ok(prefix: str, digits: str, letter: str) -> bool:
    num = {"": "", "X": "0", "Y": "1", "Z": "2"}[(prefix or "").upper()] + digits
    return len(num) == 8 and DNI_LETTERS[int(num) % 23] == letter.upper()


def _iban_ok(raw: str) -> bool:
    s = raw.replace(" ", "").upper()
    s = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in s)) % 97 == 1


def _luhn_ok(raw: str) -> bool:
    d = [int(c) for c in re.sub(r"\D", "", raw)][::-1]
    return 13 <= len(d) <= 19 and sum(x if i % 2 == 0 else (x * 2 - 9 if x * 2 > 9 else x * 2) for i, x in enumerate(d)) % 10 == 0


def mask_pii(text: str) -> tuple[str, list[str]]:
    found = []

    def sub(rx, tag, check=None):
        nonlocal text

        def repl(m):
            if check and not check(m):
                return m.group(0)
            found.append(tag)
            return f"<{tag}>"
        text = rx.sub(repl, text)

    sub(EMAIL, "EMAIL")
    sub(IBAN, "IBAN", lambda m: _iban_ok(m.group(0)))
    sub(CARD, "TARJETA", lambda m: _luhn_ok(m.group(0)))
    sub(DNI_NIE, "DNI_NIE", lambda m: _dni_ok(m.group(1), m.group(2).zfill(8 if not m.group(1) else 7), m.group(3)))
    sub(PHONE, "TELEFONO")
    return text, sorted(set(found))


# ------------------------------------------------------------------ 2 · Model Armor
_lock = threading.Lock()
_session: AuthorizedSession | None = None
_genai: genai.Client | None = None


def armor(text: str, response: bool = False) -> list[str]:
    """Matched filter names ([] = clean). Fail open is NOT allowed: an error raises and sg-api answers 503."""
    global _session
    with _lock:
        if _session is None:
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            _session = AuthorizedSession(creds)
    method, field = ("sanitizeModelResponse", "modelResponseData") if response else ("sanitizeUserPrompt", "userPromptData")
    r = _session.post(f"{ARMOR_URL}:{method}", json={field: {"text": text}}, timeout=10)
    r.raise_for_status()
    hits = []
    for name, res in (r.json()["sanitizationResult"].get("filterResults") or {}).items():
        for v in res.values():   # each filter wraps its result in its own key (piAndJailbreakFilterResult, raiFilterResult...)
            if isinstance(v, dict) and v.get("matchState") == "MATCH_FOUND":
                if name == "rai":
                    hits += [k for k, t in (v.get("raiFilterTypeResults") or {}).items() if t.get("matchState") == "MATCH_FOUND"]
                else:
                    hits.append(name)
    return hits


# ------------------------------------------------------------------ 3 · topic (Gemini, typed)
TOPIC_PROMPT = """Eres el filtro de temas de StoreGear, un asistente interno para empleados de una tienda de deporte que
vende relojes inteligentes (Garmin, Polar, Suunto). Decide si el mensaje del empleado está DENTRO del ámbito:
- productos, especificaciones, funciones y uso de relojes y accesorios; comparativas; precio y stock;
- políticas y temas internos de la tienda (devoluciones, descuentos, garantías, márgenes, objetivos, procedimientos);
- saludos, agradecimientos y preguntas sobre qué puede hacer el asistente.
Fuera del ámbito: cualquier otra cosa (recetas, tareas escolares, programación, política, ocio, cultura general...).
Si dudas, considera que está DENTRO. Responde solo con el JSON pedido.

Mensaje: <mensaje>{text}</mensaje>"""
# one try, 8 s at most: past that the question goes on without it (agents.gcp_events), never waits on a slow endpoint
TOPIC_TIMEOUT_MS = 8000
TOPIC_SCHEMA = types.Schema(type="OBJECT", required=["on_topic"], properties={"on_topic": types.Schema(type="BOOLEAN")})


def on_topic(text: str) -> bool:
    global _genai
    with _lock:
        if _genai is None:
            _genai = genai.Client(vertexai=True, project=PROJECT, location="eu")
    r = _genai.models.generate_content(
        model=MODEL, contents=TOPIC_PROMPT.format(text=text.replace("</mensaje>", "")),
        config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json", response_schema=TOPIC_SCHEMA,
                                           thinking_config=types.ThinkingConfig(thinking_level="low"),
                                           http_options=types.HttpOptions(timeout=TOPIC_TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1))))
    return bool(json.loads(r.text)["on_topic"])


# ------------------------------------------------------------------ 4 · leaks (deterministic)
PROMPT_FILE = Path(os.getenv("STOREGEAR_PROMPT_FILE", Path(__file__).parent / "system_es.md"))
LEAK_TERMS = re.compile(r"buscar_catalogo_hibrido|consultar_precio_stock|\bfileId\b|\bparentId\b|<\s*/?\s*manual\b|system prompt|"
                        r"mensaje de sistema|instrucciones de sistema", re.I)
N = 12


def _words(t: str) -> list[str]:
    return re.findall(r"[a-záéíóúñü0-9]+", t.lower())


def _prompt_shingles() -> set[tuple]:
    if not PROMPT_FILE.exists():
        return set()
    text = re.sub(r'"[^"]*"', " ", PROMPT_FILE.read_text(encoding="utf-8"))   # quoted reply templates are meant to be said
    w = _words(text)
    return {tuple(w[i:i + N]) for i in range(len(w) - N + 1)}


PROMPT_SHINGLES = _prompt_shingles()


def leak(answer: str) -> str | None:
    m = LEAK_TERMS.search(answer)
    if m:
        return f"term:{m.group(0)}"
    w = _words(answer)
    overlap = sum(tuple(w[i:i + N]) in PROMPT_SHINGLES for i in range(len(w) - N + 1))
    return f"prompt:{overlap}" if overlap >= 2 else None


# ------------------------------------------------------------------ 5 · links
URL = re.compile(r"https?://[^\s)>\]]+|\bwww\.[^\s)>\]]+", re.I)


def strip_links(answer: str) -> tuple[str, int]:
    removed = 0

    def repl(m):
        nonlocal removed
        host = urlparse(m.group(0) if "://" in m.group(0) else "https://" + m.group(0)).hostname or ""
        if any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS):
            return m.group(0)
        removed += 1
        return "[enlace eliminado]"
    return URL.sub(repl, answer), removed
