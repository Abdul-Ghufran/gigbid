"""Blind pairwise human panel (B4): score classmates' A/B choices from evals/datasets/human_panel_pairs.csv.

Fill the column `which_would_you_reply_to_A_or_B` (one copy of the CSV per rater, or several raters in one file with
`rater_name`), then:
  python -m evals.runners.human_panel --csv path/to/filled.csv [--csv another.csv]
Writes evals/results/human_panel.json: shipped-pipeline win rate with a two-sided binomial test."""
import argparse
import csv
import json

from scipy import stats

from evals.runners import harness as H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="append", required=True)
    a = ap.parse_args()
    key = json.loads((H.DS / "human_panel_key.json").read_text(encoding="utf-8"))
    votes = []
    for path in a.csv:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                choice = (r.get("which_would_you_reply_to_A_or_B") or "").strip().upper()[:1]
                if choice in ("A", "B"):
                    votes.append({"pair": r["pair"], "rater": r.get("rater_name") or path, "picked": key[r["pair"]][choice]})
    wins = sum(v["picked"] == "shipped" for v in votes)
    n = len(votes)
    p = stats.binomtest(wins, n, 0.5).pvalue if n else None
    out = {"votes": n, "raters": len({v["rater"] for v in votes}), "shipped_win_rate": round(wins / n, 4) if n else None,
           "binomial_p": round(float(p), 4) if p is not None else None, "detail": votes}
    H.write("human_panel", out)
    print({k: v for k, v in out.items() if k != "detail"})


if __name__ == "__main__":
    main()
