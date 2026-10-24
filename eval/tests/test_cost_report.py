"""SMO-26 · the weekly cost report: estimated (ANSWER lines) vs billed (billing export)."""
import cost_report


def line(agent="gcp", eur=0.03, guard=None):
    return {"event": "ANSWER", "agent": agent, "cost_eur": eur if agent == "gcp" else None, "guard": guard}


def test_only_the_google_cloud_answers_are_priced():
    s = cost_report.summarize([line(eur=0.02), line(eur=0.04), line(agent="n8n")])
    assert s == {"answers": 2, "estimated_eur": 0.06, "per_answer_eur": 0.03, "blocked": 0}


def test_guard_blocks_are_counted_apart():
    s = cost_report.summarize([line(eur=0.03), line(eur=0.0, guard="input")])
    assert s["answers"] == 2 and s["blocked"] == 1


def test_no_answers_means_no_average():
    assert cost_report.summarize([]) == {"answers": 0, "estimated_eur": 0.0, "per_answer_eur": None, "blocked": 0}


def test_within_15_percent_the_price_table_holds():
    diff, ok = cost_report.compare(estimated_eur=1.00, billed_eur=1.10)
    assert round(diff, 1) == -9.1 and ok


def test_beyond_15_percent_the_price_table_is_wrong():
    diff, ok = cost_report.compare(estimated_eur=1.00, billed_eur=1.30)
    assert round(diff, 1) == -23.1 and not ok


def test_nothing_billed_cannot_be_compared():
    assert cost_report.compare(estimated_eur=0.5, billed_eur=0.0) == (None, False)
