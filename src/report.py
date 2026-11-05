"""Render README.md from README.template.md and results/metrics.json so every number and every
conclusion in the decision memo comes from the last run."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
m = json.load(open(os.path.join(ROOT, "results", "metrics.json")))
ALPHA = m["plan"]["alpha"]
s, v, plan = m["setup"], m["validity"], m["plan"]
conv, rpu, aov = m["conversion"], m["revenue_per_user"], m["order_value"]


def pct(x, signed=False):
    return f"{x:+.1%}" if signed else f"{x:.2%}"


def money(x):
    return f"{'-' if x < 0 else '+'}${abs(x):.2f}"


def sig(p):
    return "significant" if p < ALPHA else "not significant"


metric_rows = "\n".join([
    f"| Conversion (primary) | {pct(conv['control'])} | {pct(conv['treatment'])} | {pct(conv['lift'], True)} "
    f"| {pct(conv['lift_ci'][0], True)} to {pct(conv['lift_ci'][1], True)} | {conv['p']:.3f} |",
    f"| Revenue per user | ${rpu['control']:.2f} | ${rpu['treatment']:.2f} | {pct(rpu['lift'], True)} "
    f"| {money(rpu['bootstrap_ci'][0])} to {money(rpu['bootstrap_ci'][1])} (bootstrap, absolute) | {rpu['p']:.3f} |",
    f"| Order value (buyers) | ${aov['control']:.2f} | ${aov['treatment']:.2f} | {pct(aov['lift'], True)} | | {aov['p']:.3f} |",
])
seg_rows = "\n".join(
    f"| {r['segment']} | {r['users']:,} | {pct(r['control'])} | {pct(r['treatment'])} | {pct(r['lift'], True)} "
    f"| {pct(r['lift_lo'], True)} to {pct(r['lift_hi'], True)} | {r['p']:.3f} | {r['p_holm']:.3f} |"
    for r in m["segments"]
)

checks = [f"- Sample ratio: {s['control_users']:,} control vs {s['treatment_users']:,} treatment "
          f"({v['control_share']:.1%} control), chi-square p = {v['srm_p']:.2f}: "
          f"{'no sample ratio mismatch' if v['srm_p'] >= 0.01 else 'SAMPLE RATIO MISMATCH, results not trustworthy'}."]
bal = ", ".join(f"{k} p = {p:.2f}" for k, p in v["balance_p"].items())
checks.append(f"- Covariate balance across arms: {bal}"
              f"{' (randomization looks clean)' if min(v['balance_p'].values()) >= ALPHA else ' (one imbalance by chance; segment cuts below control for it)'}.")
checks.append(f"- Sample: planned {s['planned_n_per_arm']:,} users per arm over {s['planned_days']} days; got "
              f"{min(s['control_users'], s['treatment_users']):,} per arm over {s['days']} days.")
checks = "\n".join(checks)

# Decision memo, written from the numbers.
sig_segs = [r for r in m["segments"] if r["p_holm"] < ALPHA]
memo = [f"**Decision: {m['decision']}.**", ""]
memo.append(f"- Conversion moved {pct(conv['lift'], True)} (95% CI {pct(conv['lift_ci'][0], True)} to "
            f"{pct(conv['lift_ci'][1], True)}, p = {conv['p']:.3f}): {sig(conv['p'])} at alpha {ALPHA}.")
memo.append(f"- Revenue per user moved {pct(rpu['lift'], True)} (p = {rpu['p']:.2f}), {sig(rpu['p'])}. "
            f"Order value among buyers moved {pct(aov['lift'], True)} (p = {aov['p']:.3f}), so "
            f"{'part of any conversion gain is offset by smaller baskets' if aov['lift'] < 0 else 'baskets did not shrink'}.")
if sig_segs:
    names = ", ".join(f"{r['segment']} ({pct(r['lift'], True)}, Holm p = {r['p_holm']:.3f})" for r in sig_segs)
    memo.append(f"- Segments that hold up after the Holm correction: {names}. The rest are flat.")
else:
    memo.append("- No segment effect survives the Holm correction.")
if m["decision"] == "ship":
    memo.append("- Next: roll out to all users and keep conversion and order value on the weekly dashboard for a month.")
elif sig_segs:
    memo.append(f"- Next: segment results were not the pre-registered primary metric, so treat them as a lead, not a "
                f"result. Run a follow-up test of the new checkout on {sig_segs[0]['segment'].split('=')[1]} only, with "
                f"conversion as the primary metric and order value as a guardrail.")
else:
    memo.append("- Next: keep the current checkout; the change does not move the metric enough to matter.")
memo = "\n".join(memo)

pk = m["peeking"]
peeking = (f"Read daily, the cumulative test crossed p < {ALPHA} on {pk['days_significant_before_end']} of {s['days']} days "
           f"(lowest p on day {pk['min_p_day']}). "
           + ("Stopping on one of those days would have declared a win the full sample does not support, which is why the "
              "test is read once, at the planned sample size." if pk["days_significant_before_end"] and conv["p"] >= ALPHA else
              "The interval narrows steadily as data arrives; the readout uses only the planned end date."))

fill = {
    "BASELINE": f"{plan['baseline']:.1%}", "MDE": f"{plan['mde_relative']:.0%}", "POWER": f"{plan['power']:.0%}",
    "ALPHA": str(ALPHA), "N_PLAN": f"{plan['n_per_arm']:,}", "DAILY": f"{plan['daily_users']:,}",
    "DAYS_NEEDED": str(plan["days_needed"]), "DAYS_PLANNED": str(plan["days_planned"]),
    "MDE_TABLE": "\n".join(f"| {k} | {n:,} | {2 * n / plan['daily_users']:.0f} |" for k, n in plan["n_per_arm_for_mde"].items()),
    "USERS": f"{s['users']:,}", "START": s["start"], "END": s["end"],
    "CHECKS": checks, "METRICS": metric_rows, "SEGMENTS": seg_rows, "MEMO": memo, "PEEKING": peeking,
}
text = open(os.path.join(ROOT, "README.template.md")).read()
for k, val in fill.items():
    text = text.replace("{{" + k + "}}", val)
open(os.path.join(ROOT, "README.md"), "w").write(text)
print("README.md rendered")
