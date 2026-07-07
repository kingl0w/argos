#!/usr/bin/env sh
# Regenerate the GitHub Pages demo graph (docs/graph.html) from this repo's
# specs, and inject a back link to the landing page. The back link lives here,
# not in the argos-graph template — the tool stays landing-page-agnostic.
set -eu
cd "$(dirname "$0")/.."

tools/argos-graph/.venv/bin/argos-graph viz --out docs/graph.html

python3 - <<'EOF'
from pathlib import Path

p = Path("docs/graph.html")
html = p.read_text()
marker = "<h1>argos-graph</h1>"
link = marker + '\n  <p class="sub"><a href="index.html" style="color:inherit">&#8592; back to argos</a></p>'
assert marker in html, "argos-graph panel header not found; template changed?"
p.write_text(html.replace(marker, link, 1))
EOF

echo "wrote docs/graph.html (with back link)"
