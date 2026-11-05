"""Generate a synthetic checkout experiment (seeded, so every run gives the same data).

Scenario: an online store tests a one-page checkout (treatment) against the current three-step
checkout (control). Users are randomized 50/50 on their first visit during a 28-day window (the run length the power plan asks for).

The simulated ground truth, which the analysis does not get to see:
- baseline conversion depends on device and on new vs returning users (about 3.5% overall)
- the new checkout lifts conversion by about 20% on mobile and about 2% on desktop
- order value is lognormal and slightly lower in treatment (about -2%), as the shorter page drops a cross-sell row
- weekends convert a little better in both arms

Output: data/users.csv, one row per user (not committed; rerun this script).
"""
import os

import numpy as np
import pandas as pd

SEED = 7
DAYS = 28
DAILY_USERS = 3500
START = "2026-03-02"

BASE_RATE = {("desktop", "returning"): 0.052, ("desktop", "new"): 0.030,
             ("mobile", "returning"): 0.032, ("mobile", "new"): 0.018}
LIFT = {"desktop": 1.02, "mobile": 1.20}
AOV_MEAN = {"desktop": 68.0, "mobile": 54.0}
AOV_TREATMENT = 0.98
AOV_SIGMA = 0.55

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "users.csv")


def main():
    rng = np.random.default_rng(SEED)
    days = pd.date_range(START, periods=DAYS, freq="D")
    n_per_day = rng.poisson(DAILY_USERS, size=DAYS)
    date = np.repeat(days, n_per_day)
    n = len(date)

    arm = np.where(rng.random(n) < 0.5, "treatment", "control")
    device = np.where(rng.random(n) < 0.58, "mobile", "desktop")
    user_type = np.where(rng.random(n) < 0.45, "new", "returning")

    p = np.array([BASE_RATE[(d, u)] for d, u in zip(device, user_type)])
    p *= np.where(pd.DatetimeIndex(date).day_of_week >= 5, 1.10, 1.0)
    p *= np.where(arm == "treatment", np.vectorize(LIFT.get)(device), 1.0)
    converted = rng.random(n) < p

    mean = np.vectorize(AOV_MEAN.get)(device) * np.where(arm == "treatment", AOV_TREATMENT, 1.0)
    mu = np.log(mean) - AOV_SIGMA ** 2 / 2  # lognormal with the given mean
    revenue = np.where(converted, np.round(rng.lognormal(mu, AOV_SIGMA), 2), 0.0)

    df = pd.DataFrame({"user_id": np.arange(1, n + 1), "date": date.date, "arm": arm, "device": device,
                       "user_type": user_type, "converted": converted.astype(int), "revenue": revenue})
    df.to_csv(DEST, index=False)
    print(f"saved {DEST}: {n:,} users, {converted.sum():,} orders")


if __name__ == "__main__":
    main()
