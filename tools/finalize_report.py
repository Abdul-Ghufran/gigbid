"""One command to fold whatever live-model rows exist into the results, README and report, then commit and push.

Safe to run while the long runs are still going: R&D C is summarised from its per-row checkpoint (only jobs that every
architecture has finished), the judge file is written incrementally, and the model-profile table uses the live runs
that exist.
  .venv/Scripts/python.exe tools/finalize_report.py ["commit message"]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.finish_evals import finalize  # noqa: E402


def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "Fold in the latest live-model rows"
    if (ROOT / "evals" / "results" / "rq_c_architectures.open_strong.partial.json").exists():
        subprocess.run([sys.executable, "-m", "evals.runners.rq_c_architectures", "--profile", "open_strong", "--per-persona", "1",
                        "--aggregate-only"], cwd=ROOT, capture_output=True)
    finalize(msg)


if __name__ == "__main__":
    main()
