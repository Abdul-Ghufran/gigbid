"""Repository rules enforced in CI (`python -m tools.ci_checks`):
  1. no secrets committed (API keys, tokens, private keys, a real .env)
  2. nothing under gigsim/ changed since the freeze (gigsim/MANIFEST.sha256)
  3. every LLM prompt lives in agent/prompts/ (no inline prompts in agent/ or rag/ Python)
  4. every results file cited in README.md exists under evals/results/
`--freeze-gigsim` (re)writes the manifest; only done once, when the simulator was frozen.
"""
from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_RX = re.compile(r"(gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|sk-lf-[0-9a-f-]{20,}|"
                       r"AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|xox[baprs]-[A-Za-z0-9-]{10,})")
PROMPT_RX = re.compile(r"\b(you are (a|an|the)\b|return only (a )?json|ignore any instructions)", re.I)
PROMPT_ALLOW = {"agent/guards.py", "rag/query.py"}  # detection regexes, not prompts


def tracked() -> list[str]:
    return subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()


def check_secrets(files) -> list[str]:
    bad = [f for f in files if Path(f).name == ".env"]
    for f in files:
        p = ROOT / f
        if p.suffix in {".png", ".gif", ".pdf", ".mp4", ".npz", ".sqlite"} or not p.is_file() or p.stat().st_size > 5_000_000:
            continue
        try:
            if SECRET_RX.search(p.read_text(encoding="utf-8", errors="ignore")):
                bad.append(f)
        except OSError:
            pass
    return bad


def gigsim_digest() -> dict[str, str]:
    out = {}
    for p in sorted((ROOT / "gigsim").rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if p.is_file() and "/state/" not in rel and "__pycache__" not in rel and p.name != "MANIFEST.sha256":
            out[rel] = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return out


def check_gigsim() -> list[str]:
    man = ROOT / "gigsim" / "MANIFEST.sha256"
    if not man.exists():
        return ["gigsim/MANIFEST.sha256 missing"]
    want = dict(line.split("  ", 1)[::-1] for line in man.read_text().splitlines() if line.strip())
    have = gigsim_digest()
    return [f"gigsim changed: {f}" for f in sorted(set(want) | set(have)) if want.get(f) != have.get(f)]


def check_prompts() -> list[str]:
    bad = []
    for base in ("agent", "rag"):
        for p in (ROOT / base).rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if rel in PROMPT_ALLOW:
                continue
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 60 \
                        and PROMPT_RX.search(node.value) and not node.value.lstrip().startswith(('"""', "Return")):
                    bad.append(f"{rel}:{node.lineno} looks like an inline prompt")
    return bad


def check_readme_results() -> list[str]:
    readme = ROOT / "README.md"
    if not readme.exists():
        return []
    cited = set(re.findall(r"evals/results/[\w./-]+\.(?:json|csv)", readme.read_text(encoding="utf-8")))
    return [f"README cites missing {c}" for c in sorted(cited) if not (ROOT / c).exists()]


def main():
    if "--freeze-gigsim" in sys.argv:
        (ROOT / "gigsim" / "MANIFEST.sha256").write_text("".join(f"{h}  {f}\n" for f, h in gigsim_digest().items()))
        print("gigsim manifest written")
        return
    files = tracked()
    problems = [f"possible secret in {f}" for f in check_secrets(files)] + check_gigsim() + check_prompts() + check_readme_results()
    for p in problems:
        print("FAIL:", p)
    if problems:
        sys.exit(1)
    print("ci_checks: no secrets, gigsim unchanged, prompts in agent/prompts, README results traceable")


if __name__ == "__main__":
    main()
