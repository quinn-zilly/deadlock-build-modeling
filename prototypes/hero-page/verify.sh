#!/bin/sh
# PROTOTYPE verification. A page that parses can still throw on its first
# render, and on the page the two failures look identical -- so parse AND run.
set -e
cd "$(dirname "$0")"
python - <<'PY'
import re
html = open('index.html', encoding='utf-8').read()
open('_script.js', 'w', encoding='utf-8').write(re.findall(r'<script>(.*?)</script>', html, re.S)[-1])
PY
node --check data.js
node --check _script.js
cat dom_stub.js data.js _script.js checks.js > _run.js
node _run.js
rm -f _script.js _run.js
