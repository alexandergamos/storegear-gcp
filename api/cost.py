"""SMO-26 · Cost per answer (ADR-019): an estimate from the answer's tokens, reconciled weekly with the bill.

Prices are what this project is billed, not list prices: the billing export in BigQuery (billing_export,
2026-10-24) divided cost by usage per SKU. Billed in EUR; the export's USD->EUR rate that day was 0.8582.
"""

EUR_PER_TOKEN = {
    "model_in": 1.452e-6,          # Gemini 3.8 Flash Regional (EU) Text Input - Predictions
    "model_cached_in": 1.452e-7,   # Gemini 3.8 Flash Regional Text Input Caching
    "model_out": 7.260e-6,         # Gemini 3.8 Flash Regional Text Output - Predictions (thinking is billed as output)
}
EUR_PER_USD = 0.8582

# The topic check (guards.on_topic, one gemini-2.5-flash call with no thinking since 2026-10-27) doesn't report its usage here.
# It is still priced at the Gemini 3.8 Flash rates below until the billing export shows the 2.5 Flash SKU: a small overestimate.
# ~300 tokens in (ADR-015) and a short JSON out; the weekly report shows if this is off.
TOPIC_CHECK_TOKENS = (300, 20)

# Model Armor: no charge appears in the billing export for this project (free allowance). The query embedding is
# computed inside Agent Runtime and costs ~€0.000004 per question: below the estimate's precision, left out.


def estimate(usage: dict | None, topic_check: bool) -> dict:
    """{'eur', 'usd'} for one answer. `usage` sums the agent's model calls (agents.add_usage); None = no model call."""
    eur = 0.0
    if usage:
        fresh = usage["tokens_in"] - usage["tokens_cached"]
        eur += fresh * EUR_PER_TOKEN["model_in"] + usage["tokens_cached"] * EUR_PER_TOKEN["model_cached_in"]
        eur += usage["tokens_out"] * EUR_PER_TOKEN["model_out"]
    if topic_check:
        eur += TOPIC_CHECK_TOKENS[0] * EUR_PER_TOKEN["model_in"] + TOPIC_CHECK_TOKENS[1] * EUR_PER_TOKEN["model_out"]
    return {"eur": eur, "usd": eur / EUR_PER_USD}
