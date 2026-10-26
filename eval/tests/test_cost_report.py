"""SMO-26 · the weekly cost report: estimated (ANSWER lines) vs billed (billing export)."""
import subprocess

import pytest

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


def test_gcloud_is_found_on_windows_too(monkeypatch):
    # on Windows gcloud is gcloud.cmd: a bare "gcloud" in subprocess.run is not found (WinError 2)
    monkeypatch.setattr(cost_report.shutil, "which", lambda name: r"C:\SDK\bin\gcloud.cmd" if name == "gcloud" else None)
    assert cost_report.gcloud("logging", "read")[:3] == [r"C:\SDK\bin\gcloud.cmd", "logging", "read"]


def test_the_bill_is_matched_by_sku_whatever_the_service_is_called():
    # the console bills Gemini under "Agent Platform Model Garden" now, not "Vertex AI"
    q = cost_report.billed_query(7)
    assert "'Vertex AI'" not in q and "Gemini 3.8 Flash" in q
    assert "project.id = 'storegear-prod-ag26'" in q and "Gemini API" in q   # this project only, not the API-key billing


def fake_run(monkeypatch, returncode, stdout="", stderr=""):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    monkeypatch.setattr(cost_report.subprocess, "run", run)
    return seen


def test_the_log_filter_is_one_cloud_logging_accepts(monkeypatch):
    # "-P7D" is not a timestamp: Cloud Logging rejects the whole filter (INVALID_ARGUMENT); --freshness bounds the days
    seen = fake_run(monkeypatch, 0, stdout="[]")
    cost_report.answer_lines(7)
    flt = next(a for a in seen["cmd"] if "jsonPayload.event" in a)
    assert "timestamp" not in flt and "--freshness=7d" in seen["cmd"]


def test_a_failed_log_read_stops_the_report_instead_of_counting_zero(monkeypatch):
    fake_run(monkeypatch, 1, stderr="ERROR: (gcloud.logging.read) INVALID_ARGUMENT")
    with pytest.raises(SystemExit) as e:
        cost_report.answer_lines(7)
    assert "INVALID_ARGUMENT" in str(e.value)
