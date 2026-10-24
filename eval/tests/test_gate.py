"""SMO-28 · the release gate over the 22-question eval (ADR-018)."""
import json

import pytest

import gate

BASELINE = {"correctness": 5.00, "faithfulness": 4.95, "context_relevance": 5.00, "answer_relevance": 5.00}


def row(qid, score=5, answer="Sí, hasta 50 m."):
    return {"qid": qid, "answer": answer, "latency_s": 3.0, "correctness": score, "faithfulness": score,
            "context_relevance": score, "answer_relevance": score}


def test_only_availability_errors_are_retried():
    results = [row(1), row(2, score=1, answer="ERROR 503: unavailable"), row(3, score=2, answer="Resiste 5 ATM.")]
    assert gate.retry_list(results) == [2]   # Q3 is a wrong answer: never retried


def test_a_rerun_replaces_only_the_rows_it_ran():
    first = [row(1), row(2, score=1, answer="ERROR 503"), row(3)]
    rerun = [row(2)]
    merged = gate.merge(first, rerun)
    assert [r["qid"] for r in merged] == [1, 2, 3]
    assert merged[1]["answer"] == "Sí, hasta 50 m."


def test_the_summary_is_the_mean_of_each_metric():
    s = gate.summarize([row(1, 5), row(2, 4)])
    assert s["correctness"] == 4.5 and s["faithfulness"] == 4.5 and s["n"] == 2


def test_a_metric_more_than_a_tenth_below_the_baseline_fails():
    ok, problems = gate.verdict({"correctness": 4.85, "faithfulness": 4.95, "context_relevance": 5.0, "answer_relevance": 5.0}, BASELINE)
    assert not ok
    assert problems == ["correctness 4.85 < 4.90 (baseline 5.00 - 0.1)"]


def test_within_a_tenth_passes():
    ok, problems = gate.verdict({"correctness": 4.91, "faithfulness": 4.85, "context_relevance": 5.0, "answer_relevance": 4.9}, BASELINE)
    assert ok and problems == []


def test_an_availability_error_left_after_the_retry_fails_the_gate(tmp_path):
    first = tmp_path / "first.json"
    first.write_text(json.dumps({"results": [row(1), row(2, score=5, answer="ERROR 503")]}), encoding="utf-8")
    assert gate.main([str(first)]) == 1


def test_the_command_passes_a_good_run(tmp_path, capsys):
    first = tmp_path / "first.json"
    rerun = tmp_path / "rerun.json"
    first.write_text(json.dumps({"results": [row(1), row(2, score=1, answer="ERROR 503")]}), encoding="utf-8")
    rerun.write_text(json.dumps({"results": [row(2)]}), encoding="utf-8")
    assert gate.main([str(first), str(rerun)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_retry_list_command_prints_the_qids(tmp_path, capsys):
    first = tmp_path / "first.json"
    first.write_text(json.dumps({"results": [row(4, answer="ERROR 504"), row(7, answer="ERROR 503")]}), encoding="utf-8")
    assert gate.main(["--retry-list", str(first)]) == 0
    assert capsys.readouterr().out.strip() == "4 7"


def test_a_question_the_judge_could_not_score_is_retried():
    unscored = {**row(3), "correctness": None, "faithfulness": None}   # the judge's endpoint failed, not the agent
    assert gate.retry_list([row(1), unscored]) == [3]


def test_a_metric_with_no_scored_answer_has_no_mean():
    assert gate.mean_scored([{**row(1), "correctness": None}], "correctness") is None


def test_a_run_with_nothing_scored_fails_with_a_reason(tmp_path, capsys):
    first = tmp_path / "first.json"
    nothing = {"qid": 1, "answer": "No he podido responder.", "correctness": None, "faithfulness": None,
               "context_relevance": None, "answer_relevance": None}
    first.write_text(json.dumps({"results": [nothing]}), encoding="utf-8")
    assert gate.main([str(first)]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "correctness: no answer scored" in out


@pytest.mark.parametrize("metric", ["correctness", "faithfulness", "context_relevance", "answer_relevance"])
def test_every_metric_is_gated(metric):
    s = {**BASELINE, metric: BASELINE[metric] - 0.2}
    assert not gate.verdict(s, BASELINE)[0]
