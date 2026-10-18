"""Live price & stock from the 'StoreGear' Google Sheet (tab 'Catalogo'), looked up by fileId.

Same contract as the n8n `consultar_precio_stock` tool: read live on EVERY call (prompt rule 2), never cached.
Access: the sheet is shared with sg-agent as Viewer (Drive sharing, not IAM, ADR-002).
Scopes: the Sheets API needs a token with the spreadsheets scope. Runtime (metadata) credentials only carry
cloud-platform and ignore requested scopes (403 in Agent Runtime), so the tool always asks the IAM credentials API
for a scoped token AS sg-agent: locally by impersonation (STOREGEAR_IMPERSONATE_SA), in the cloud by
self-impersonation (STOREGEAR_SHEETS_SA; sg-agent holds Token Creator on itself).
"""
from __future__ import annotations

import os

import google.auth
from google.auth import impersonated_credentials
from google.auth.transport.requests import AuthorizedSession

SHEET_ID = os.getenv("STOREGEAR_PRICE_SHEET_ID", "1KnKC0iFDCzChg9szTkDazkwmgqQGQpbDg2raZ0EI2m4")
TAB = os.getenv("STOREGEAR_PRICE_SHEET_TAB", "Catalogo")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

_session: AuthorizedSession | None = None


def _sheets() -> AuthorizedSession:
    global _session
    if _session is None:
        base, _ = google.auth.default(scopes=SCOPES + ["https://www.googleapis.com/auth/cloud-platform"])
        sa = os.getenv("STOREGEAR_IMPERSONATE_SA") or os.getenv("STOREGEAR_SHEETS_SA")
        creds = impersonated_credentials.Credentials(source_credentials=base, target_principal=sa, target_scopes=SCOPES) if sa else base
        _session = AuthorizedSession(creds)
    return _session


def lookup_price_stock(file_id: str) -> dict:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{TAB}"
    r = _sheets().get(url, timeout=10)
    r.raise_for_status()
    rows = r.json().get("values", [])
    if not rows:
        return {"status": "error", "message": "price sheet is empty"}
    header, data = rows[0], rows[1:]
    for row in data:
        rec = dict(zip(header, row + [""] * (len(header) - len(row))))
        if rec.get("fileId", "").strip() == file_id.strip():
            return {"status": "success", "model": rec.get("model"), "price": rec.get("price"),
                    "currency": rec.get("currency"), "stockQty": rec.get("stockQty"),
                    "stockStatus": rec.get("stockStatus"), "lastUpdated": rec.get("lastUpdated"),
                    "source": "live price sheet"}
    return {"status": "not_found", "message": "Este producto no aparece en la hoja de precios."}
