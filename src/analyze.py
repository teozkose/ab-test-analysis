"""Analyze the experiment: validity checks first, then the primary metric, secondary metrics and segments.

Writes results/metrics.json, results/segments.csv, results/daily.csv and two figures.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
ALPHA = 0.05
N_BOOT = 2000
SEED = 11


def conversion_test(c, t):
    """Two-proportion z-test and a Newcombe CI for the difference (treatment minus control)."""
    x = np.array([t["converted"].sum(), c["converted"].sum()])
    n = np.array([len(t), len(c)])
    z, p = proportions_ztest(x, n)
    lo, hi = confint_proportions_2indep(x[0], n[0], x[1], n[1], method="newcomb")
    pc, pt = x[1] / n[1], x[0] / n[0]
    return {"control": pc, "treatment": pt, "diff": pt - pc, "ci": [lo, hi],
            "lift": pt / pc - 1, "lift_ci": [lo / pc, hi / pc], "z": z, "p": p}


def bootstrap_diff(a, b, rng):
    """Percentile bootstrap CI for mean(b) - mean(a)."""
    da = rng.choice(a, size=(N_BOOT, len(a))).mean(axis=1)
    db = rng.choice(b, size=(N_BOOT, len(b))).mean(axis=1)
    return list(np.percentile(db - da, [2.5, 97.5]))


def mean_test(a, b, rng=None):
    t, p = stats.ttest_ind(b, a, equal_var=False)
    out = {"control": a.mean(), "treatment": b.mean(), "diff": b.mean() - a.mean(),
           "lift": b.mean() / a.mean() - 1, "t": t, "p": p}
    if rng is not None:
        out["bootstrap_ci"] = bootstrap_diff(a, b, rng)
    return out


def main():
    df = pd.read_csv(os.path.join(ROOT, "data", "users.csv"), parse_dates=["date"])
    plan = json.load(open(os.path.join(RESULTS, "plan.json")))
    rng = np.random.default_rng(SEED)
    c, t = df[df["arm"] == "control"], df[df["arm"] == "treatment"]

    # 1. Validity: sample ratio mismatch and covariate balance.
    srm_p = stats.chisquare([len(c), len(t)]).pvalue
    balance = {col: stats.chi2_contingency(pd.crosstab(df["arm"], df[col]))[1] for col in ["device", "user_type"]}

    # 2. Primary: conversion. 3. Secondary: revenue per user (all users) and order value (buyers only).
    conv = conversion_test(c, t)
    rpu = mean_test(c["revenue"].to_numpy(), t["revenue"].to_numpy(), rng)
    aov = mean_test(c.loc[c["converted"] == 1, "revenue"].to_numpy(), t.loc[t["converted"] == 1, "revenue"].to_numpy())

    # 4. Segments, with a Holm correction because four cuts are tested.
    rows = []
    for col in ["device", "user_type"]:
        for level, g in df.groupby(col):
            r = conversion_test(g[g["arm"] == "control"], g[g["arm"] == "treatment"])
            rows.append({"segment": f"{col}={level}", "users": len(g), "control": r["control"], "treatment": r["treatment"],
                         "lift": r["lift"], "lift_lo": r["lift_ci"][0], "lift_hi": r["lift_ci"][1], "p": r["p"]})
    seg = pd.DataFrame(rows)
    seg["p_holm"] = multipletests(seg["p"], method="holm")[1]
    seg.round(5).to_csv(os.path.join(RESULTS, "segments.csv"), index=False)

    # 5. Cumulative results by day, to show why the test is read once at the planned end.
    daily = []
    for d in sorted(df["date"].unique()):
        sub = df[df["date"] <= d]
        r = conversion_test(sub[sub["arm"] == "control"], sub[sub["arm"] == "treatment"])
        daily.append({"date": pd.Timestamp(d).date().isoformat(), "users": len(sub), "lift": r["lift"],
                      "lift_lo": r["lift_ci"][0], "lift_hi": r["lift_ci"][1], "p": r["p"]})
    daily = pd.DataFrame(daily)
    daily.round(5).to_csv(os.path.join(RESULTS, "daily.csv"), index=False)
    early_sig_days = int((daily["p"] < ALPHA).sum())

    # Decision rule, fixed before the readout: ship if conversion is significantly up and revenue per user is not
    # significantly down.
    ship = conv["p"] < ALPHA and conv["ci"][0] > 0 and not (rpu["p"] < ALPHA and rpu["diff"] < 0)
    metrics = {
        "setup": {"users": len(df), "control_users": len(c), "treatment_users": len(t), "days": df["date"].nunique(),
                  "start": df["date"].min().date().isoformat(), "end": df["date"].max().date().isoformat(),
                  "planned_n_per_arm": plan["n_per_arm"], "planned_days": plan["days_planned"]},
        "plan": plan,
        "validity": {"srm_p": srm_p, "control_share": len(c) / len(df), "balance_p": balance},
        "conversion": conv, "revenue_per_user": rpu, "order_value": aov,
        "segments": seg.to_dict(orient="records"),
        "peeking": {"days_significant_before_end": early_sig_days, "first_day_p": daily["p"].iloc[0],
                    "min_p_day": int(daily["p"].idxmin()) + 1},
        "decision": "ship" if ship else "do not ship",
    }
    json.dump(metrics, open(os.path.join(RESULTS, "metrics.json"), "w"), indent=2, default=float)

    # Figure: lift with 95% CI overall and per segment.
    fig, ax = plt.subplots(figsize=(7, 3.8))
    labels = ["overall"] + seg["segment"].tolist()
    lifts = [conv["lift"]] + seg["lift"].tolist()
    lo = [conv["lift_ci"][0]] + seg["lift_lo"].tolist()
    hi = [conv["lift_ci"][1]] + seg["lift_hi"].tolist()
    y = np.arange(len(labels))[::-1]
    ax.errorbar(np.array(lifts) * 100, y, xerr=[(np.array(lifts) - lo) * 100, (np.array(hi) - lifts) * 100],
                fmt="o", color="#2b6cb0", capsize=3)
    ax.axvline(0, color="grey", lw=1)
    ax.set_yticks(y, labels)
    ax.set(xlabel="Relative conversion lift, % (95% CI)", title="New checkout: conversion lift by segment")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "lift_by_segment.png"), dpi=120)

    # Figure: cumulative lift and p-value by day.
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True)
    x = pd.to_datetime(daily["date"])
    a1.plot(x, daily["lift"] * 100, color="#2b6cb0")
    a1.fill_between(x, daily["lift_lo"] * 100, daily["lift_hi"] * 100, alpha=0.2, color="#2b6cb0")
    a1.axhline(0, color="grey", lw=1)
    a1.set(ylabel="Cumulative lift, %", title="Cumulative conversion lift as data arrives")
    a2.plot(x, daily["p"], color="#c05621")
    a2.axhline(ALPHA, color="grey", ls="--", lw=1)
    a2.set(ylabel="p-value", yscale="log")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "cumulative.png"), dpi=120)

    print(f"conversion lift {conv['lift']:+.1%} (p={conv['p']:.4f}); RPU diff {rpu['diff']:+.3f} (p={rpu['p']:.3f}); "
          f"decision: {metrics['decision']}")


if __name__ == "__main__":
    main()
