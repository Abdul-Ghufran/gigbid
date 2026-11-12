"""One command to fold whatever live-model rows exist into the results, README and report, then commit and push.

Safe to run while the long runs are still going: R&D C is summarised from its per-row checkpoint (only jobs that every
architecture has finished), the judge file is written incrementally, and the model-profile table uses the live runs
that exist.
  .\gb.cmd tools/finalize_report.py ["commit message"]
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.finish_evals import finalize  # noqa: E402


def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "Fold in the latest live-model rows"
    res = ROOT / "evals" / "results"
    if (res / "rq_c_architectures.open_strong.partial.json").exists():
        # keep the sample size of the last full run (jobs = 3 personas x per-persona)
        per = max(1, json.loads((res / "rq_c_architectures.json").read_text(encoding="utf-8")).get("jobs", 3) // 3) \
            if (res / "rq_c_architectures.json").exists() else 1
        subprocess.run([sys.executable, "-m", "evals.runners.rq_c_architectures", "--profile", "open_strong", "--per-persona", str(per),
                        "--aggregate-only"], cwd=ROOT, capture_output=True)
    finalize(msg)


if __name__ == "__main__":
    main()
