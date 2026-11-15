"""Build a one-page picker for the blind pairwise panel (SUBMISSION_GUIDE Step 6).

  .\\gb.cmd tools/panel_helper.py        -> writes evals/datasets/panel_helper.html and opens it

Shows one job with proposals A and B side by side (sides are already randomised; which one is the shipped pipeline is
hidden in human_panel_key.json). Click A or B (or press the key). "Save CSV" downloads human_panel_votes_<name>.csv in the
format evals/runners/human_panel.py reads.  The choices must be yours: this is the human half of the panel.
"""
import csv
import json
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "evals" / "datasets" / "human_panel_pairs.csv"
OUT = ROOT / "evals" / "datasets" / "panel_helper.html"

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Blind Proposal Panel</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#5f5f5a;--line:#dedcd6;--accent:#2f5bd3;--sel:#e7eeff;--ok:#1f7a45}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1e1e1e;--ink:#ecebe7;--muted:#a3a29c;--line:#34332f;--accent:#7d9cff;--sel:#24304f;--ok:#5fc48a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,Segoe UI,sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 0 2px}.sub{color:var(--muted);margin:0 0 12px;font-size:14px}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
button,input{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:7px 12px}
button{cursor:pointer}button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.dots{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px}.dot{width:30px;height:28px;padding:0;font-size:12px}
.dot.done{background:var(--sel)}.dot.cur{outline:2px solid var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.card h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:0 0 6px}
.title{font-weight:600;margin-bottom:6px}.txt{white-space:pre-wrap;font-size:15px}
.job .txt{max-height:180px;overflow:auto}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}@media(max-width:800px){.grid{grid-template-columns:1fr}}
.pick{width:100%;margin-top:10px;padding:12px;font-weight:600}.pick.on{background:var(--sel);border-color:var(--accent)}
.prop.on{border-color:var(--accent)}.ok{color:var(--ok);font-weight:600}
</style></head><body><div class="wrap">
<h1>Blind proposal panel</h1>
<p class="sub">You are the client who posted this job. Read both proposals and pick the one you would <b>reply to</b>.
Which pipeline wrote which is hidden and the sides are shuffled. Keys: <b>A</b> / <b>B</b> to pick, <b>←/→</b> to move.</p>
<div class="bar"><label>Your name <input id="name" placeholder="e.g. Abdul Ghufran" size="22"></label>
<button id="prev">← Prev</button><button id="next">Next →</button><span id="count"></span><span style="flex:1"></span>
<button class="primary" id="save">Save CSV</button></div>
<div class="dots" id="dots"></div>
<div class="card job"><h2>Job <span id="num"></span></h2><div class="title" id="jt"></div><div class="txt" id="jd"></div></div>
<div class="grid">
<div class="card prop" id="cardA"><h2>Proposal A</h2><div class="txt" id="pa"></div><button class="pick" data-v="A">I'd reply to A</button></div>
<div class="card prop" id="cardB"><h2>Proposal B</h2><div class="txt" id="pb"></div><button class="pick" data-v="B">I'd reply to B</button></div>
</div>
<p class="sub" id="msg"></p>
</div>
<script>
const ITEMS = __DATA__;
const KEY = "gigbid-panel-votes-v1";
let st = {votes: {}, name: ""};
try { st = Object.assign(st, JSON.parse(localStorage.getItem(KEY) || "{}")); } catch (e) {}
let i = ITEMS.findIndex(it => !st.votes[it.pair]); if (i < 0) i = 0;
const $ = id => document.getElementById(id);
function persist(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
$("name").value = st.name || ""; $("name").oninput = e => { st.name = e.target.value; persist(); };
function render(){
  const it = ITEMS[i], v = st.votes[it.pair] || "";
  $("num").textContent = `${i+1} of ${ITEMS.length}`; $("jt").textContent = it.job_title; $("jd").textContent = it.job_description;
  $("pa").textContent = it.proposal_A; $("pb").textContent = it.proposal_B;
  $("cardA").classList.toggle("on", v === "A"); $("cardB").classList.toggle("on", v === "B");
  document.querySelectorAll(".pick").forEach(b => b.classList.toggle("on", b.dataset.v === v));
  const done = ITEMS.filter(x => st.votes[x.pair]).length;
  $("count").innerHTML = done === ITEMS.length ? `<span class="ok">All ${done} picked: type your name, click Save CSV</span>` : `${done} / ${ITEMS.length} picked`;
  $("dots").innerHTML = ITEMS.map((x,k) => `<button class="dot ${st.votes[x.pair]?"done":""} ${k===i?"cur":""}" data-k="${k}">${st.votes[x.pair]||k+1}</button>`).join("");
  document.querySelectorAll(".dot").forEach(b => b.onclick = () => { i = +b.dataset.k; render(); });
}
function pick(v){ st.votes[ITEMS[i].pair] = v; persist(); if (i < ITEMS.length-1) i++; render(); window.scrollTo(0,0); }
document.querySelectorAll(".pick").forEach(b => b.onclick = () => pick(b.dataset.v));
$("prev").onclick = () => { if (i>0) i--; render(); };
$("next").onclick = () => { if (i<ITEMS.length-1) i++; render(); };
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT") return;
  const k = e.key.toUpperCase();
  if (k === "A" || k === "B") pick(k);
  if (e.key === "ArrowRight") $("next").click(); if (e.key === "ArrowLeft") $("prev").click();
});
$("save").onclick = () => {
  const name = (st.name || "").trim();
  if (!name) { $("msg").textContent = "Type your name first (it is the rater_name column)."; $("name").focus(); return; }
  const q = v => '"' + String(v ?? "").replace(/"/g,'""') + '"';
  const rows = [["pair","job_title","which_would_you_reply_to_A_or_B","rater_name"].join(",")]
    .concat(ITEMS.map(it => [it.pair, it.job_title, st.votes[it.pair] || "", name].map(q).join(",")));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + rows.join("\r\n")], {type:"text/csv"}));
  a.download = "human_panel_votes.csv"; a.click();
  const missing = ITEMS.filter(x => !st.votes[x.pair]).length;
  $("msg").textContent = (missing ? `Saved (${missing} still unpicked). ` : "Saved. ") +
    "Move human_panel_votes.csv from Downloads into evals\\datasets\\ and tell Claude it's done.";
};
render();
</script></body></html>
"""


def main():
    with open(SHEET, encoding="utf-8-sig") as f:
        items = [{k: r[k] for k in ("pair", "job_title", "job_description", "proposal_A", "proposal_B")} for r in csv.DictReader(f)]
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(PAGE.replace("__DATA__", data), encoding="utf-8")
    print(f"Wrote {OUT} ({len(items)} pairs)")
    if "--no-open" not in sys.argv:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
