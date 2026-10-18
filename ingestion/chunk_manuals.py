"""SMO-17 · Table-aware chunking of the parsed manuals -> data/catalog_v2/{chunks,parents}.csv

    uv run python ingestion/chunk_manuals.py

- Sections follow the Markdown headings; header_path = "<file> > <h1> > <h2> ...".
- Parent = a section (split above PARENT_MAX chars at block boundaries): what the agent reads.
- Child chunks = what search ranks:
    * every TABLE ROW is its own chunk, written to stand alone: "Impermeabilidad: 30 m (ISO 22810...)" for
      label|value tables, "Modo smartwatch — <col>: <cell>; <col>: <cell>" for wider tables. A row with an empty
      label continues the row above (the Document AI split-row pattern).
    * prose packed up to CHILD_MAX chars at sentence boundaries.
- Boilerplate sections (warranty, trademarks, conformity...) are skipped by their own title (n8n rule A5).
- Cross-manual duplicates: a section with the same title and >= DUP_SIM similar text in >= 3 manuals is stored
  ONCE under the pseudo-manual "Polar · información común" (file_id "polar-common"), so it stops crowding results.
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "parsed" / "full"
OUT = ROOT / "data" / "catalog_v2"
CHILD_MAX, PARENT_MAX, DUP_SIM = 600, 8000, 0.8
SKIP_TITLES = re.compile(r"garant[ií]a|warranty|marcas comerciales|trademark|copyright|derechos de autor|declaraci[oó]n de conformidad|"
                         r"conformidad|licencia|license|eliminaci[oó]n|reciclaje|disposal|aviso legal|descargo|disclaimer|normativ|regulator", re.I)
COMMON = ("polar-common", "Polar · información común")


def file_ids() -> dict[str, str]:
    ids = {}
    for line in (ROOT / "data" / "pdf" / "full" / "file_ids.tsv").read_text(encoding="utf-8-sig").splitlines():
        fid, name = line.split("\t")
        ids[name.strip()] = fid.strip()
    return ids


def sections(md: str, file_name: str) -> list[dict]:
    """Split Markdown into sections: {title, path, lines}."""
    stack: list[tuple[int, str]] = []
    out, cur = [], {"title": file_name, "path": file_name, "lines": []}
    for line in md.splitlines():
        if line.startswith("<!-- page"):
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            if any(x.strip() for x in cur["lines"]):
                out.append(cur)
            level, title = len(m.group(1)), m.group(2).strip().strip("*")
            stack = [s for s in stack if s[0] < level] + [(level, title)]
            cur = {"title": title, "path": " > ".join([file_name] + [t for _, t in stack]), "lines": []}
        else:
            cur["lines"].append(line)
    if any(x.strip() for x in cur["lines"]):
        out.append(cur)
    return out


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table_rows(block: list[str]) -> list[str]:
    rows = [cells(l) for l in block if not re.match(r"^\|?\s*:?-{3,}", l.strip())]
    if not rows:
        return []
    out: list[str] = []
    if max(len(r) for r in rows) <= 2:          # label | value: every row is data (often no real header)
        for r in rows:
            label, value = (r + [""])[:2]
            if not label and out:
                out[-1] += " / " + value
            elif label or value:
                out.append(f"{label} {value}".strip() if label.endswith(":") else f"{label}: {value}".strip(": "))
    else:                                         # wide table: first row = column headers
        head, body = rows[0], rows[1:]
        for r in body:
            label = r[0] if r else ""
            parts = [f"{h}: {c}" for h, c in zip(head[1:], r[1:]) if c]
            if not label and out:
                out[-1] += " / " + "; ".join(parts)
            elif label or parts:
                out.append(f"{label} — " + "; ".join(parts) if parts else label)
    return out


def chunks_of(lines: list[str]) -> list[str]:
    """Children of one section: one per table row, prose packed to CHILD_MAX."""
    out, prose, table = [], [], []

    def flush_prose():
        text = " ".join(p.strip() for p in prose if p.strip())
        prose.clear()
        buf = ""
        for sent in re.split(r"(?<=[.!?:])\s+", text):
            if len(buf) + len(sent) > CHILD_MAX and buf:
                out.append(buf.strip())
                buf = ""
            buf += sent + " "
        if buf.strip():
            out.append(buf.strip())

    for line in lines + [""]:
        if line.strip().startswith("|"):
            if prose:
                flush_prose()
            table.append(line)
            continue
        if table:
            out.extend(table_rows(table))
            table.clear()
        if line.strip():
            prose.append(line)
        elif prose:
            flush_prose()
    return [c for c in out if len(c) > 2]


def shingles(t: str) -> set[str]:
    s = re.sub(r"[^a-z0-9áéíóúñ]", "", t.lower())
    return {s[i:i + 6] for i in range(max(len(s) - 5, 0))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / max(len(a | b), 1)


def main() -> None:
    ids = file_ids()
    secs = []
    for md_path in sorted(SRC.glob("*.md")):
        name = md_path.stem + ".pdf"
        for s in sections(md_path.read_text(encoding="utf-8"), name):
            if SKIP_TITLES.search(s["title"]):
                continue
            s.update(file_name=name, file_id=ids[name], body="\n".join(s["lines"]).strip())
            secs.append(s)

    # cross-manual duplicates -> one common copy
    by_title = defaultdict(list)
    for s in secs:
        by_title[re.sub(r"\W+", " ", s["title"].lower()).strip()].append(s)
    dup_ids, common = set(), []
    for title, group in by_title.items():
        if len({s["file_name"] for s in group}) < 3:
            continue
        ref = shingles(group[0]["body"])
        similar = [s for s in group if jaccard(ref, shingles(s["body"])) >= DUP_SIM]
        if len({s["file_name"] for s in similar}) >= 3:
            dup_ids |= {id(s) for s in similar}
            c = dict(group[0], file_id=COMMON[0], file_name=COMMON[1], path=f"{COMMON[1]} > {group[0]['title']}")
            common.append(c)
    kept = [s for s in secs if id(s) not in dup_ids] + common

    OUT.mkdir(parents=True, exist_ok=True)
    n_children = n_rows = 0
    counters = defaultdict(int)
    with open(OUT / "chunks.csv", "w", encoding="utf-8", newline="") as fc, open(OUT / "parents.csv", "w", encoding="utf-8", newline="") as fp:
        wc = csv.writer(fc)
        wp = csv.writer(fp)
        wc.writerow(["child_id", "parent_id", "file_id", "file_name", "header_path", "chunk_text", "product_category", "access_level"])
        wp.writerow(["parent_id", "file_id", "header_path", "parent_context"])
        for s in kept:
            access = "manager" if "Interno" in s["file_name"] else "staff"
            body = s["body"]
            parts = [body[i:i + PARENT_MAX] for i in range(0, len(body), PARENT_MAX)] or [body]
            for part in parts:
                pid = f"{s['file_id']}::p{counters[s['file_id']]}"
                counters[s["file_id"]] += 1
                wp.writerow([pid, s["file_id"], s["path"], part])
                for j, ch in enumerate(chunks_of(part.splitlines())):
                    wc.writerow([f"{pid}::c{j}", pid, s["file_id"], s["file_name"], s["path"], ch, "smartwatch", access])
                    n_children += 1
                    n_rows += ch.count(":") > 0 and len(ch) < 300
    print(f"sections {len(secs)} -> kept {len(kept)} (common {len(common)}, duplicates folded {len(dup_ids)}) · "
          f"parents {sum(counters.values())} · chunks {n_children}")
    for c in common:
        print("  common:", c["title"][:70])


if __name__ == "__main__":
    main()
