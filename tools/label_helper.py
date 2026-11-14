"""Build a one-page labelling helper for the 30 judge-calibration items (SUBMISSION_GUIDE Step 4).

  .\\gb.cmd tools/label_helper.py        -> writes evals/datasets/label_helper.html and opens it

The page shows one job + proposal at a time with the rubric, lets you click a 1-5 score (and add a note), keeps your
progress in the browser, and "Save CSV" downloads judge_calibration_sheet.csv in the same format the kappa runner reads.
Scores must be yours: kappa measures agreement between a human and the LLM judge.
"""
import csv
import json
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "evals" / "datasets" / "judge_calibration_sheet.csv"
OUT = ROOT / "evals" / "datasets" / "label_helper.html"

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Judge Labelling</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#5f5f5a;--line:#dedcd6;--accent:#2f5bd3;--sel:#e7eeff;--ok:#1f7a45}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1e;--ink:#ecebe7;--muted:#a3a29c;--line:#34332f;--accent:#7d9cff;--sel:#24304f;--ok:#5fc48a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,Segoe UI,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 0 2px}.sub{color:var(--muted);margin:0 0 14px;font-size:14px}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:7px 12px;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.dots{display:flex;gap:4px;flex-wrap:wrap}.dot{width:26px;height:26px;border-radius:6px;font-size:12px;padding:0;display:grid;place-items:center}
.dot.done{background:var(--sel)}.dot.cur{outline:2px solid var(--accent)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:800px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.card h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:0 0 6px}
.title{font-weight:600;margin-bottom:6px}.txt{white-space:pre-wrap;font-size:15px}
.scores{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0}
@media(max-width:600px){.scores{grid-template-columns:1fr}}
.score{text-align:left;padding:10px}.score b{font-size:20px;display:block}.score span{font-size:13px;color:var(--muted)}
.score.on{background:var(--sel);border-color:var(--accent)}
textarea{width:100%;font:inherit;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);padding:8px}
details{margin:10px 0}summary{cursor:pointer;color:var(--accent)}ul{margin:6px 0 0 18px;padding:0}
.ok{color:var(--ok);font-weight:600}
</style></head><body><div class="wrap">
<h1>Judge calibration labelling</h1>
<p class="sub">Read the job, then the proposal, and give the score <b>you</b> think it deserves. Don't overthink it: about 30–60 s per item.
Keys: <b>1–5</b> to score, <b>←/→</b> to move.</p>
<details open><summary>Rubric: what each score means</summary>
<ul>
<li><b>5 Excellent</b>: answers this client's actual need; evidence is <i>relevant</i> to their requirements with concrete results; clear plan and next step. You'd hire this person.</li>
<li><b>4 Good</b>: relevant and backed by evidence, but one weakness (one requirement not covered, a slightly generic part, or a vague plan).</li>
<li><b>3 OK / generic</b>: on topic, but could be sent to many similar jobs; evidence is thin or only partly relevant.</li>
<li><b>2 Weak</b>: mostly generic or mismatched evidence (projects that don't relate to what the client asked); key requirements ignored.</li>
<li><b>1 Bad</b>: irrelevant, unbelievable, broken or empty text, or wrong job entirely.</li>
</ul>
<p class="sub" style="margin-top:6px">Quick checks: (1) Does it address what <i>this</i> client asked for? (2) Is the evidence related to those requirements? (3) Are there specific results? (4) Is there a clear plan / next step? (5) Does it read naturally?</p>
</details>
<div class="bar"><button id="prev">← Prev</button><button id="next">Next →</button>
<span id="count"></span><span style="flex:1"></span><button class="primary" id="save">Save CSV</button></div>
<div class="dots" id="dots"></div>
<div style="height:10px"></div>
<div class="grid">
<div class="card"><h2>Job <span id="num"></span></h2><div class="title" id="jt"></div><div class="txt" id="jd"></div></div>
<div class="card"><h2>Proposal</h2><div class="txt" id="pr"></div></div>
</div>
<div class="scores" id="scores"></div>
<textarea id="note" rows="2" placeholder="Optional note: why this score (helps you explain it in the viva)"></textarea>
<p class="sub" id="msg"></p>
</div>
<script>
const ITEMS = __DATA__;
const KEY = "gigbid-judge-labels-v1";
const LABELS = ["Bad","Weak","OK / generic","Good","Excellent"];
let st = {};
try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { st = {}; }
ITEMS.forEach(it => { if (!st[it.item]) st[it.item] = {score: it.your_score_1_to_5 || "", note: it.notes || ""}; });
let i = ITEMS.findIndex(it => !st[it.item].score); if (i < 0) i = 0;
const $ = id => document.getElementById(id);
function persist(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
function render(){
  const it = ITEMS[i], s = st[it.item];
  $("num").textContent = `${i+1} of ${ITEMS.length}`; $("jt").textContent = it.job_title;
  $("jd").textContent = it.job_description; $("pr").textContent = it.proposal; $("note").value = s.note;
  $("scores").innerHTML = LABELS.map((l,k) => `<button class="score ${String(s.score)===String(k+1)?"on":""}" data-v="${k+1}"><b>${k+1}</b><span>${l}</span></button>`).join("");
  document.querySelectorAll(".score").forEach(b => b.onclick = () => setScore(b.dataset.v));
  const done = ITEMS.filter(x => st[x.item].score).length;
  $("count").innerHTML = done === ITEMS.length ? `<span class="ok">All ${done} scored: click Save CSV</span>` : `${done} / ${ITEMS.length} scored`;
  $("dots").innerHTML = ITEMS.map((x,k) => `<button class="dot ${st[x.item].score?"done":""} ${k===i?"cur":""}" data-k="${k}">${st[x.item].score||k+1}</button>`).join("");
  document.querySelectorAll(".dot").forEach(b => b.onclick = () => { i = +b.dataset.k; render(); });
}
function setScore(v){ st[ITEMS[i].item].score = v; persist(); if (i < ITEMS.length-1) i++; render(); window.scrollTo(0,0); }
$("note").oninput = e => { st[ITEMS[i].item].note = e.target.value; persist(); };
$("prev").onclick = () => { if (i>0) i--; render(); };
$("next").onclick = () => { if (i<ITEMS.length-1) i++; render(); };
document.addEventListener("keydown", e => {
  if (e.target.tagName === "TEXTAREA") return;
  if ("12345".includes(e.key) && e.key) setScore(e.key);
  if (e.key === "ArrowRight") $("next").click(); if (e.key === "ArrowLeft") $("prev").click();
});
$("save").onclick = () => {
  const q = v => '"' + String(v ?? "").replace(/"/g,'""') + '"';
  const rows = [["item","job_title","job_description","proposal","your_score_1_to_5","notes"].join(",")]
    .concat(ITEMS.map(it => [it.item,it.job_title,it.job_description,it.proposal,st[it.item].score,st[it.item].note].map(q).join(",")));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + rows.join("\r\n")], {type:"text/csv"}));
  a.download = "judge_calibration_sheet.csv"; a.click();
  const missing = ITEMS.filter(x => !st[x.item].score).length;
  $("msg").textContent = (missing ? `Saved (${missing} still unscored). ` : "Saved. ") +
    "Move the downloaded file into evals\\datasets\\ (replace the old one), then run the two commands in SUBMISSION_GUIDE Step 4.";
};
render();
</script></body></html>
"""


def main():
    with open(SHEET, encoding="utf-8-sig") as f:
        items = list(csv.DictReader(f))
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(PAGE.replace("__DATA__", data), encoding="utf-8")
    print(f"Wrote {OUT} ({len(items)} items)")
    if "--no-open" not in sys.argv:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
