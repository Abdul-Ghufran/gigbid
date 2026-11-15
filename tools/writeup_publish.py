"""Make a paste-ready version of docs/WRITEUP.md for Medium / LinkedIn articles (SUBMISSION_GUIDE Step 7).

  .\\gb.cmd tools/writeup_publish.py      -> docs/writeup_publish.html (opens in the browser)

Medium and LinkedIn articles have no tables, so the results table becomes a bullet list; everything else (headings,
bold, italics, links, lists) survives copy-paste.  The page has two buttons: "Copy title" and "Copy article body".
"""
import html
import re
import sys
import webbrowser
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "WRITEUP.md"
OUT = ROOT / "docs" / "writeup_publish.html"


def table_to_list(md: str) -> str:
    """Turn each pipe table into '- **Row**: Header = value; Header = value' bullets."""
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and re.match(r"^\|[-| ]+\|$", lines[i + 1]):
            head = [c.strip() for c in lines[i].strip("|").split("|")]
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                pairs = "; ".join(f"{h}: {c}" for h, c in zip(head[1:], cells[1:]))
                out.append(f"- **{cells[0]}**: {pairs}")
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def main():
    md = SRC.read_text(encoding="utf-8")
    title = md.splitlines()[0].lstrip("# ").strip()
    body_md = table_to_list("\n".join(md.splitlines()[1:]).strip())
    body = markdown.markdown(body_md, extensions=["extra"])
    words = len(re.findall(r"\b\w+\b", re.sub(r"<[^>]+>", " ", body))) + len(title.split())
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Write-up: paste-ready</title>
<style>
body{{margin:0;background:#f4f3ef;color:#1d1d1b;font:16px/1.6 Georgia,serif}}
.bar{{position:sticky;top:0;background:#1d1d1b;color:#fff;padding:10px 16px;display:flex;gap:10px;align-items:center;
flex-wrap:wrap;font:14px system-ui,sans-serif}}
button{{font:600 14px system-ui,sans-serif;border:0;border-radius:6px;padding:8px 14px;cursor:pointer;background:#fff}}
button.main{{background:#3b6cf6;color:#fff}}#msg{{color:#9fe0b4}}
.paper{{max-width:720px;margin:20px auto;background:#fff;padding:24px 32px;border-radius:8px}}
h1.t{{font-size:30px;line-height:1.25;margin:0 0 6px}}.note{{color:#666;font:13px system-ui,sans-serif;margin:0 0 18px}}
#body h2{{font-size:22px;margin:28px 0 8px}}a{{color:#1a5fb4}}
</style></head><body>
<div class="bar"><b>Paste-ready write-up</b> · {words} words
<button id="ct">1. Copy title</button><button class="main" id="cb">2. Copy article body</button><span id="msg"></span></div>
<div class="paper"><h1 class="t" id="title">{html.escape(title)}</h1>
<p class="note">Title above goes in the Medium/LinkedIn title field; everything below is the body. The results table is a
list because Medium and LinkedIn articles have no tables.</p>
<div id="body">{body}</div></div>
<script>
function copyNode(id, label){{
  const r = document.createRange(); r.selectNodeContents(document.getElementById(id));
  const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  let ok = false; try {{ ok = document.execCommand("copy"); }} catch (e) {{}}
  s.removeAllRanges();
  document.getElementById("msg").textContent = ok ? label + " copied - now paste it (Ctrl+V)" : "Select it with the mouse and press Ctrl+C";
}}
document.getElementById("ct").onclick = () => copyNode("title", "Title");
document.getElementById("cb").onclick = () => copyNode("body", "Article body");
</script></body></html>"""
    OUT.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT} ({words} words)")
    if "--no-open" not in sys.argv:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
