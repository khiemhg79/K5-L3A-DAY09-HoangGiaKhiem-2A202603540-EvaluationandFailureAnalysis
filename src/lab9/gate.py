"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _bad_number(v) -> bool:
    return isinstance(v, float) and (math.isnan(v) or math.isinf(v))


def _graded_ids(spec: dict) -> list[str]:
    """Spec metrics that come from a per-row grader (the ones a crashed grader can null out)."""
    return [m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS]


def _looser(new: dict | None, old: dict | None) -> list[str]:
    """Ways threshold `new` is laxer than `old` (missing new = dropped = looser)."""
    old = old or {}
    if new is None:
        return ["removed"]
    out = []
    if "max" in old and ("max" not in new or new["max"] > old["max"]):
        out.append(f"max {old['max']} -> {new.get('max')}")
    if "min" in old and ("min" not in new or new["min"] < old["min"]):
        out.append(f"min {old['min']} -> {new.get('min')}")
    if "max_increase" in old and ("max_increase" not in new or new["max_increase"] > old["max_increase"]):
        out.append(f"max_increase {old['max_increase']} -> {new.get('max_increase')}")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    return out


def ratchet_check(spec: dict, base_spec: dict, same_eval_set: bool = False) -> list[str]:
    """Same eval-set version => every threshold may only get stricter (metrics and slices).
    same_eval_set=True (PR and baseline reports share eval_set_sha): renaming the version while the
    items are unchanged does not reset the ratchet."""
    problems = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        if not same_eval_set:
            return []                               # genuinely new eval set: thresholds start again
        problems.append(f"ratchet: eval_set_version {base_spec.get('eval_set_version')!r} -> "
                        f"{spec.get('eval_set_version')!r} but the eval set itself did not change")
    cur = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        new = cur.get(m["id"])
        if new is None:
            problems.append(f"ratchet: metric {m['id']} removed from the spec")
            continue
        for why in _looser(new.get("threshold"), m.get("threshold")):
            problems.append(f"ratchet: metric {m['id']} threshold looser ({why})")
        if m.get("blocking") and not new.get("blocking"):
            problems.append(f"ratchet: metric {m['id']} no longer blocking")
    key = lambda sl: (sl.get("name"), sl.get("metric"))
    cur_sl = {key(sl): sl for sl in spec.get("slices") or []}
    for sl in base_spec.get("slices") or []:
        new = cur_sl.get(key(sl))
        sid = f"{sl.get('name')}/{sl.get('metric')}"
        if new is None:
            problems.append(f"ratchet: slice {sid} removed from the spec")
            continue
        for why in _looser(new, sl):
            problems.append(f"ratchet: slice {sid} looser ({why})")
        if sl.get("blocking") and not new.get("blocking"):
            problems.append(f"ratchet: slice {sid} no longer blocking")
    for k in ("eval_set", "labels", "seeds"):
        if k in base_spec and spec.get(k) != base_spec.get(k):
            problems.append(f"ratchet: spec {k} changed without a new eval_set_version")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Catches: NaN/inf metrics, dropped or duplicated rows, a changed (item, seed) set, grader
    failures / None scores, a manifest that disagrees with the rows, a loosened spec (ratchet),
    and items relabelled out of a slice."""
    problems: list[str] = []
    rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    man = pr.get("manifest") or {}

    # 1. Metric values must be real numbers (NaN < min is False, so a naive gate passes it).
    for k, v in (pr.get("metrics") or {}).items():
        if _bad_number(v):
            problems.append(f"metric {k} is {v}")
    for r in rows:
        for k, v in r.items():
            if _bad_number(v):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} {k} is {v}")
                break

    # 2. Row count: every item x every seed, exactly once -- against the PR manifest AND the baseline.
    base_man = base.get("manifest") or {}
    want = int(base_man.get("items") or 0) * len(base_man.get("seeds") or [])
    if int(man.get("items") or 0) != int(base_man.get("items") or 0) or list(man.get("seeds") or []) != list(base_man.get("seeds") or []):
        problems.append(f"manifest items/seeds {man.get('items')}x{man.get('seeds')} differ from the baseline's "
                        f"{base_man.get('items')}x{base_man.get('seeds')}")
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, baseline manifest needs {want} (items x seeds): dropped or duplicated rows")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        problems.append(f"duplicated (item, seed) rows: {dups[:3]}")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        miss, extra = base_keys - set(keys), set(keys) - base_keys
        problems.append(f"(item, seed) set differs from the baseline: {len(miss)} missing, {len(extra)} extra")
    if {r.get("seed") for r in rows} != set(man.get("seeds") or []):
        problems.append("seeds in rows do not match the manifest seeds")
    if len({r.get("item_id") for r in rows}) != int(man.get("items") or 0):
        problems.append("item count in rows does not match the manifest")

    # 3. Grader health: a crashed grader must never silently drop out of the mean.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    for mid in _graded_ids(spec):
        if any(mid in r for r in base_rows) or any(mid in r for r in rows):
            nulls = [r for r in rows if r.get(mid) is None]
            if nulls:
                problems.append(f"{len(nulls)} row(s) with no score for graded metric {mid} (grader crashed?)")
    for m in spec.get("metrics") or []:
        if m.get("blocking") and m["id"] in (base.get("metrics") or {}) and (pr.get("metrics") or {}).get(m["id"]) is None:
            problems.append(f"blocking metric {m['id']} missing from the PR report")

    # 4. Ratchet: same eval-set version => thresholds only get stricter.
    if base_spec is not None:
        same = (pr.get("manifest") or {}).get("eval_set_sha") == base_man.get("eval_set_sha")
        problems += ratchet_check(spec, base_spec, same_eval_set=same)

    # 5. Slice tags come from labels; a PR may not move an item out of a slice.
    base_slices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    moved = sorted({r.get("item_id") for r in rows
                    if r.get("item_id") in base_slices and sorted(r.get("slices") or []) != base_slices[r.get("item_id")]})
    if moved:
        problems.append(f"slice tags differ from the baseline for {moved[:5]}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a = per_item(pr, metric, slice_name=name)
        b = per_item(base, metric, slice_name=name)
        verdict, note = "ok", ""
        if not a:
            verdict, val = "missing", None              # an empty slice cannot vouch for anything
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} n={len(a):<3} {json.dumps(th):<36} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())