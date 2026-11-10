"""Insert the headline results tables (from evals/results via results_table.py) into README.md between markers."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, "-m", "evals.runners.results_table"], cwd=ROOT, check=True, capture_output=True)
tables = (ROOT / "evals" / "results" / "results_tables.md").read_text(encoding="utf-8")
keep = []
for section in re.split(r"(?m)^## ", tables)[1:]:
    title = section.split("\n", 1)[0]
    if title.startswith(("B5.", "R&D C.", "R&D A.", "B4.", "E4.", "Change request", "X2.", "Where better")):
        keep.append("### " + section.strip())
block = "\n\n".join(keep) + "\n\nMore: retrieval variants V0–V9, ablation by persona and job type, claim-verifier calibration -> " \
                            "[`evals/results/results_tables.md`](evals/results/results_tables.md)."
readme = (ROOT / "README.md").read_text(encoding="utf-8")
readme = re.sub(r"<!-- RESULTS:START -->.*<!-- RESULTS:END -->", "<!-- RESULTS:START -->\n" + block.replace("\\", "\\\\") + "\n<!-- RESULTS:END -->",
                readme, flags=re.S)
(ROOT / "README.md").write_text(readme, encoding="utf-8")
print("README results updated")
