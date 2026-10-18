"""SMO-16 · Parser bake-off on 3 excerpts with known traps. Writes Markdown per parser to data/parsed/ and scores it.

    uv run python ingestion/parser_test.py gemini
    uv run python ingestion/parser_test.py docai --processor <PROCESSOR_ID>

Traps (what a good parser must keep, as text an index can find):
- Ignite 2 specs table: "Impermeabilidad: 30 m" on its own row, with ISO 22810 (eval Q6).
- Instinct 3 battery table: the second line of a merged cell, "Hasta 7 días con Pant siempre enc" (45 mm) and
  "Hasta 9 días" (50 mm), in the right columns (LlamaParse dropped it in n8n, backlog A20).
- Suunto Ocean battery modes: Rendimiento, Resistencia, Ultra, Tour (prose control).
"""
import argparse
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data" / "pdf"
OUT = ROOT / "data" / "parsed"
PROJECT = "storegear-prod-ag26"
TESTS = {
    "test_ignite2_specs.pdf": [r"Impermeabilidad[^\n]{0,40}30\s?m", r"ISO\s?22810"],
    "test_instinct3_battery.pdf": [r"7 d[ií]as[^\n]{0,60}siempre", r"9 d[ií]as[^\n]{0,60}siempre", r"solo GPS[^\n]{0,80}32 horas[^\n]{0,40}40 horas"],
    "test_suunto_battery.pdf": [r"Rendimiento", r"Resistencia", r"Ultra", r"Tour"],
}

GEMINI_PROMPT = """Convierte este fragmento de manual en Markdown fiel, para indexarlo en un buscador.
Reglas:
- Copia el texto tal cual, en espanol. No resumas, no traduzcas, no anadas nada.
- Mantén los titulos como encabezados Markdown (#, ##, ###).
- Cada tabla como tabla Markdown: una fila por fila real, todas las celdas, incluidas las celdas con varias lineas
  (une sus lineas con " / "). Repite la cabecera de columna si hace falta para que cada fila se entienda sola.
- Ignora numeros de pagina, cabeceras y pies repetidos."""


def parse_gemini(pdf: Path) -> str:
    client = genai.Client(vertexai=True, project=PROJECT, location="eu")
    r = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[types.Part.from_bytes(data=pdf.read_bytes(), mime_type="application/pdf"), GEMINI_PROMPT],
        config=types.GenerateContentConfig(temperature=0, thinking_config=types.ThinkingConfig(thinking_level="low")))
    return r.text


def parse_docai(pdf: Path, processor: str) -> str:
    from google.api_core.client_options import ClientOptions
    from google.cloud import documentai
    client = documentai.DocumentProcessorServiceClient(client_options=ClientOptions(api_endpoint="eu-documentai.googleapis.com"))
    name = client.processor_path(PROJECT, "eu", processor)
    req = documentai.ProcessRequest(name=name, raw_document=documentai.RawDocument(content=pdf.read_bytes(), mime_type="application/pdf"))
    doc = client.process_document(request=req).document
    return layout_to_markdown(doc)


def layout_to_markdown(doc) -> str:
    """Flatten Document AI layout blocks (text, headings, tables, lists) into Markdown."""
    lines = []

    def text_of(block):
        return (block.text_block.text if block.text_block else "").strip()

    def walk(blocks):
        for b in blocks:
            if b.text_block and b.text_block.text:
                t = b.text_block.type_ or ""
                prefix = "#" * min(int(t[-1]), 4) + " " if t.startswith("heading-") and t[-1].isdigit() else ""
                lines.append(prefix + b.text_block.text.strip())
                walk(b.text_block.blocks)
            elif b.table_block:
                rows = list(b.table_block.header_rows) + list(b.table_block.body_rows)
                for i, row in enumerate(rows):
                    cells = [" / ".join(text_of(x) for x in c.blocks if text_of(x)) for c in row.cells]
                    lines.append("| " + " | ".join(cells) + " |")
                    if i == 0:
                        lines.append("|" + " --- |" * len(cells))
            elif b.list_block:
                for e in b.list_block.list_entries:
                    walk(e.blocks)
    walk(doc.document_layout.blocks)
    return "\n".join(lines)


def score(name: str, md: str) -> tuple[int, int, list[str]]:
    missed = [p for p in TESTS[name] if not re.search(p, md, re.IGNORECASE)]
    return len(TESTS[name]) - len(missed), len(TESTS[name]), missed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("parser", choices=["gemini", "docai"])
    ap.add_argument("--processor", default="")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    total = [0, 0]
    for name in TESTS:
        t0 = time.time()
        md = parse_gemini(PDF / name) if a.parser == "gemini" else parse_docai(PDF / name, a.processor)
        (OUT / f"{a.parser}_{name.removesuffix('.pdf')}.md").write_text(md, encoding="utf-8")
        ok, n, missed = score(name, md)
        total[0] += ok
        total[1] += n
        print(f"{a.parser:6} {name:28} {ok}/{n}  {time.time() - t0:5.1f}s  {len(md):6} chars  missed: {missed}")
    print(f"{a.parser}: {total[0]}/{total[1]} traps kept")
