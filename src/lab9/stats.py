"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import comb

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _norm(xs: Sequence[str]) -> list[str]:
    return [str(x).strip().upper() for x in xs]


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    h, j = _norm(human), _norm(judge)
    if len(h) != len(j):
        raise ValueError(f"length mismatch: {len(h)} human vs {len(j)} judge labels")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for a, b in zip(h, j):
        if b == POS:
            cm["tp" if a == POS else "fp"] += 1
        else:
            cm["fn" if a == POS else "tn"] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    p = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    r = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    h, j = _norm(human), _norm(judge)
    if len(h) != len(j) or not h:
        raise ValueError("kappa needs two non-empty label lists of the same length")
    n = len(h)
    p_o = sum(a == b for a, b in zip(h, j)) / n
    cats = set(h) | set(j)
    p_e = sum((h.count(c) / n) * (j.count(c) / n) for c in cats)
    if abs(1.0 - p_e) < 1e-12:
        raise ValueError("kappa undefined: expected agreement is 1 (constant labels)")
    return (p_o - p_e) / (1.0 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1.0
    if denom <= 0:
        raise ValueError("Rogan-Gladen undefined: sensitivity + specificity must exceed 1")
    est = (observed_rate + specificity - 1.0) / denom
    return min(1.0, max(0.0, est))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy import stats as sps

    xa, xb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if xa.shape != xb.shape:
        raise ValueError("paired bootstrap needs the same items in the same order")
    if xa.size == 0 or np.array_equal(xa, xb):
        return (0.0, 0.0, 0.0)
    diff = float(xa.mean() - xb.mean())
    if np.all(xa - xb == xa[0] - xb[0]):            # constant difference: CI collapses to a point
        return (diff, diff, diff)
    res = sps.bootstrap((xa, xb), lambda x, y, axis=-1: x.mean(axis=axis) - y.mean(axis=axis),
                        paired=True, vectorized=True, n_resamples=n_resamples,
                        confidence_level=confidence, method="percentile",
                        rng=np.random.default_rng(rng))
    return (diff, float(res.confidence_interval.low), float(res.confidence_interval.high))


def _check_k(n: int, c: int, k: int) -> None:
    if not (0 <= c <= n) or k < 1 or k > n:
        raise ValueError(f"need 0 <= c <= n and 1 <= k <= n, got n={n} c={c} k={k}")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_k(n, c, k)
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_k(n, c, k)
    return comb(c, k) / comb(n, k)