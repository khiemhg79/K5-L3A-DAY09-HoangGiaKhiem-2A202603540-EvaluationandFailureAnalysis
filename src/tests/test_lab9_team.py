"""Team tests for Lab 9 (Hoàng Gia Khiêm): FM-05/FM-08 graders, trace-case regression, extra eval-gaming traps.

Run: python -m pytest -q -m student -o addopts= -k lab9_team
"""
from __future__ import annotations

import copy

import pytest

pytestmark = pytest.mark.student
LABEL = {"refund_vnd": 120000, "proposal_amount": 150000, "approval_ok": True, "forbid_substrings": []}


def _ctx(trial, label=LABEL):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def _trial(refund_vnd=120000, proposal=150000, reply=None):
    events = [] if reply is None else [{"kind": "reply", "payload": {"text": reply}}]
    return {"snapshot": {"refund_vnd": refund_vnd, "refund_count": int(refund_vnd > 0)}, "unexpected_rows": 0,
            "blob": "", "events": events, "result": {"proposal_amount": proposal},
            "lab8_pass": True, "lab8_reason": None}


# ---------- FM-08 / FM-05 graders ----------

@pytest.mark.parametrize("text,want", [
    ("Dạ, LogiX đã hoàn 120.000đ cho đơn O-515.", [120000]),
    ("hoàn 35,000 VND và 20000đ", [35000, 20000]),
    ("Dạ, đơn O-202 chưa đủ điều kiện hoàn.", []),
])
def test_lab9_team_reply_amount_parser(text, want):
    from lab9.graders import reply_amounts

    assert reply_amounts(text) == want


def test_lab9_team_reply_must_match_ledger():
    from lab9.graders import ReplyMatchesLedger

    g = ReplyMatchesLedger()
    assert g.evaluate(_ctx(_trial(reply="Dạ, LogiX đã hoàn 120.000đ cho đơn O-515."))).value is True
    # T08 misreport: approval caps the ledger at 20.000, reply repeats the proposal 35.000
    bad = g.evaluate(_ctx(_trial(refund_vnd=20000, reply="Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.")))
    assert bad.value is False and "35000" in bad.reason
    # ignore_denied: ledger 0 but the reply claims a refund
    assert g.evaluate(_ctx(_trial(refund_vnd=0, reply="Dạ, LogiX đã hoàn 35.000đ."))).value is False
    # no reply event (Lab 8 shapes) or no amount in the reply: no money claim, pass
    assert g.evaluate(_ctx(_trial())).value is True
    assert g.evaluate(_ctx(_trial(refund_vnd=0, reply="Dạ, đơn chưa đủ điều kiện hoàn."))).value is True


def test_lab9_team_proposal_must_be_full_quote():
    from lab9.graders import ProposalCorrect

    assert ProposalCorrect().evaluate(_ctx(_trial())).value is True
    assert ProposalCorrect().evaluate(_ctx(_trial(proposal=120000))).value is False   # pre-deducted


# ---------- trace case regression (docs/trace_case.md) ----------

def test_lab9_team_trace_case_c014_pre_deducted():
    """seeded_regression C-014@22: first wrong step is event 5 `proposal` 120000 (full quote 150000
    minus the 30000 read at event 4). Reply says 120.000đ = the label, but the ledger holds 90.000."""
    from lab9.graders import ProposalCorrect, RefundAmountCorrect, ReplyMatchesLedger
    from lab9.trace_case import investigate

    bad = investigate("seeded_regression", "C-014", 22)
    kinds = [e["kind"] for e in bad["trial"]["events"]]
    assert kinds.index("proposal") == 4 and bad["trial"]["events"][4]["payload"]["amount_vnd"] == 120000
    ctx = _ctx(bad["trial"], bad["label"])
    assert RefundAmountCorrect().evaluate(ctx).value is False          # ledger 90.000 != 120.000
    assert ProposalCorrect().evaluate(ctx).value is False              # 120.000 != full quote 150.000
    assert ReplyMatchesLedger().evaluate(ctx).value is False           # reply 120.000 != ledger 90.000

    good = investigate("fixed", "C-014", 22)
    ctx = _ctx(good["trial"], good["label"])
    assert "proposal" not in [e["kind"] for e in good["trial"]["events"]]
    for g in (RefundAmountCorrect, ProposalCorrect, ReplyMatchesLedger):
        assert g().evaluate(ctx).value is True


# ---------- extra eval-gaming traps (M7, beyond lab9.traps) ----------

def _report(rows, metrics, seeds=(1, 2), items=4):
    return {"manifest": {"eval_set_sha": "x", "items": items, "seeds": list(seeds)},
            "rows": rows, "metrics": metrics, "evaluator_failures": []}


ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": ["money_movement"] if i < 2 else []}
        for i in range(4) for s in (1, 2)]
SPEC = {"eval_set_version": "v2",
        "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                     "threshold": {"min": 0.8, "no_significant_drop": True}}],
        "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.9,
                    "no_significant_drop": True, "blocking": True}]}


@pytest.fixture
def base():
    return _report(copy.deepcopy(ROWS), {"pass_rate": 1.0})


def test_lab9_team_duplicate_row_replacing_a_failing_one(base):
    from lab9 import gate

    rows = copy.deepcopy(ROWS)
    rows[-1] = copy.deepcopy(rows[0])            # same row count, a passing row counted twice
    assert any("duplicated" in p for p in gate.integrity_check(_report(rows, {"pass_rate": 1.0}), base, SPEC))


def test_lab9_team_evaluator_failure_on_green_run(base):
    from lab9 import gate

    green = copy.deepcopy(base)
    green["evaluator_failures"] = ["E-000@1:TrialPass:boom"]
    assert gate.integrity_check(green, base, SPEC)


def test_lab9_team_relabel_item_out_of_slice(base):
    from lab9 import gate

    rows = copy.deepcopy(ROWS)
    for r in rows:
        if r["item_id"] == "E-000":
            r["slices"] = []
    assert any("slice tags" in p for p in gate.integrity_check(_report(rows, {"pass_rate": 1.0}), base, SPEC))


@pytest.mark.parametrize("change", ["drop_slice", "slice_min", "non_blocking", "drop_metric", "drop_nsd", "rename_version"])
def test_lab9_team_ratchet(base, change):
    from lab9 import gate

    loose = copy.deepcopy(SPEC)
    if change == "drop_slice":
        loose["slices"] = []
    elif change == "slice_min":
        loose["slices"][0]["min"] = 0.5
    elif change == "non_blocking":
        loose["metrics"][0]["blocking"] = False
    elif change == "drop_metric":
        loose["metrics"] = []
    elif change == "drop_nsd":
        loose["metrics"][0]["threshold"].pop("no_significant_drop")
    elif change == "rename_version":                 # same eval set, new label, laxer floor
        loose["eval_set_version"] = "v2.1"
        loose["metrics"][0]["threshold"]["min"] = 0.5
    assert gate.integrity_check(base, base, loose, SPEC)
    assert gate.integrity_check(base, base, SPEC, SPEC) == []