"""Plan the test before looking at results: sample size per arm and run length for a target effect.

Writes the plan into results/plan.json and a power curve to results/power_curve.png.
"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")

# Planning inputs: last quarter's checkout conversion and traffic, and the smallest lift worth shipping.
BASELINE = 0.035
MDE_RELATIVE = 0.10
ALPHA = 0.05
POWER = 0.80
DAILY_USERS = 3500


def n_per_arm(baseline, mde_rel, alpha=ALPHA, power=POWER):
    h = proportion_effectsize(baseline * (1 + mde_rel), baseline)
    return math.ceil(NormalIndPower().solve_power(effect_size=h, alpha=alpha, power=power, ratio=1.0))


def main():
    os.makedirs(RESULTS, exist_ok=True)
    n = n_per_arm(BASELINE, MDE_RELATIVE)
    days = math.ceil(2 * n / DAILY_USERS)
    weeks = math.ceil(days / 7)  # run whole weeks so weekdays and weekends are balanced
    plan = {"baseline": BASELINE, "mde_relative": MDE_RELATIVE, "alpha": ALPHA, "power": POWER,
            "daily_users": DAILY_USERS, "n_per_arm": n, "days_needed": days, "days_planned": weeks * 7,
            "n_per_arm_for_mde": {f"{m:.0%}": n_per_arm(BASELINE, m) for m in (0.05, 0.10, 0.15, 0.20)}}
    json.dump(plan, open(os.path.join(RESULTS, "plan.json"), "w"), indent=2)

    fig, ax = plt.subplots(figsize=(7, 4))
    sizes = np.linspace(5_000, 150_000, 200)
    for m in (0.05, 0.10, 0.15):
        h = proportion_effectsize(BASELINE * (1 + m), BASELINE)
        ax.plot(sizes / 1000, NormalIndPower().power(h, sizes, ALPHA), label=f"{m:.0%} relative lift")
    ax.axhline(POWER, color="grey", ls="--", lw=1)
    ax.axvline(n / 1000, color="grey", ls=":", lw=1)
    ax.set(xlabel="Users per arm (thousands)", ylabel="Power",
           title=f"Power at {BASELINE:.1%} baseline conversion, alpha {ALPHA}")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "power_curve.png"), dpi=120)
    print(f"plan: {n:,} users per arm, {days} days of traffic, run {weeks * 7} days")


if __name__ == "__main__":
    main()
