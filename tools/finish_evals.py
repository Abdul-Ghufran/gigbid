"""Unattended finisher for the live-model evaluations that need fresh Groq daily quota.

Waits until each model accepts a large request, then runs (strict mode: wait on quota, no fallback models):
  1. LLM judge on the 30-item calibration sheet + both proposal sets        (gpt-oss-20b, profile open_mid)
  2. live proposals, open profile (writer/critic gpt-oss-120b)              -> proposals_best_live.json
  3. R&D question C: ReAct vs supervisor vs graph (gpt-oss-120b)          -> rq_c_architectures.json
  4. live proposals, open_mid profile (all gpt-oss-20b)                     -> proposals_best_live_mid.json
  5. model_profiles.json, results tables, README, report PDF; commit + push
Each step is skipped if its result file already exists (safe to re-run).  Log: data/processed/finish_log.txt
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evals" / "results"
LOG = ROOT / "data" / "processed" / "finish_log.txt"
PY = sys.executable
ENV = {**os.environ, "LLM_WAIT_ON_QUOTA": "1", "LLM_NO_FALLBACK": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def key():
    from common.settings import get_settings

    return get_settings().groq_api_key


def wait_for(model: str, need_tokens: int = 4000, max_hours: float = 30):
    t0 = time.time()
    while time.time() - t0 < max_hours * 3600:
        try:
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key()}"}, timeout=60,
                           json={"model": model, "messages": [{"role": "user", "content": "Say OK."}], "max_tokens": need_tokens})
            if r.status_code == 200:
                log(f"{model} available")
                return True
            log(f"{model} not yet available ({r.status_code}): {r.text[:160]}")
        except Exception as e:
            log(f"probe error {e}")
        time.sleep(600)
    return False


def run(args, env_extra=None, timeout_h=6):
    cmd = [PY, *args]
    log("RUN " + " ".join(args))
    try:
        p = subprocess.run(cmd, cwd=ROOT, env={**ENV, **(env_extra or {})}, capture_output=True, text=True, timeout=timeout_h * 3600,
                           encoding="utf-8", errors="replace")
        log(f"exit {p.returncode}; tail: {p.stdout[-600:]!r} {p.stderr[-400:]!r}")
        return p.returncode == 0
    except subprocess.TimeoutExpired:
        log("TIMEOUT")
        return False


def main():
    log("finisher started")
    if not (RES / "judge_scores.json").exists() and wait_for("openai/gpt-oss-20b"):
        run(["-m", "evals.runners.judge_calibration", "--judge"], {"MODEL_PROFILE": "open_mid"})
    if not (RES / "proposals_best_live.json").exists() and wait_for("openai/gpt-oss-120b"):
        run(["-m", "evals.runners.gigsim_outcomes", "--profile", "open", "--per-persona", "1", "--tag", "best_live"])
    if not (RES / "rq_c_architectures.json").exists() and wait_for("openai/gpt-oss-120b"):
        run(["-m", "evals.runners.rq_c_architectures", "--profile", "open", "--per-persona", "2"])
    if not (RES / "proposals_best_live_mid.json").exists() and wait_for("openai/gpt-oss-20b"):
        run(["-m", "evals.runners.gigsim_outcomes", "--profile", "open_mid", "--per-persona", "1", "--tag", "best_live_mid"])
    profiles = {}
    for tag, prof in (("best_live", "open"), ("best_live_mid", "open_mid")):
        p = RES / f"proposals_{tag}.json"
        if p.exists():
            profiles[prof] = json.loads(p.read_text(encoding="utf-8"))["summary"]
    if profiles:
        (RES / "model_profiles.json").write_text(json.dumps({"generated_by": "tools/finish_evals.py", "profiles": profiles}, indent=1), encoding="utf-8")
    run(["-m", "evals.runners.results_table"])
    run(["tools/update_readme.py"])
    run(["tools/build_report.py"])
    subprocess.run(["node", "scripts/render_pdf.mjs"], cwd=ROOT / "apps" / "web")
    run(["-m", "tools.ci_checks"])
    subprocess.run(["git", "add", "-A"], cwd=ROOT)
    subprocess.run(["git", "commit", "-q", "-m", "Live-model evaluations (judge, live proposals, R&D C, model profiles); regenerate results, README and report"], cwd=ROOT)
    for _ in range(5):
        if subprocess.run(["git", "push", "-q", "origin", "main"], cwd=ROOT).returncode == 0:
            log("pushed")
            break
        time.sleep(30)
    log("finisher done")


if __name__ == "__main__":
    main()
