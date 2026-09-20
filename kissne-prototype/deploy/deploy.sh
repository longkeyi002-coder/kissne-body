#!/usr/bin/env bash
set -euo pipefail

# Deploy the existing Kissne prototype UI unchanged under:
#   https://yeqingxu.cyou/kissne/
#
# This script ONLY stages static files and installs a location snippet.
# It deliberately does not guess or rewrite the live yeqingxu.cyou vhost.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${ROOT}/kissne-prototype/prototype"
DEST="${KISSNE_WEB_ROOT:-/var/www/kissne-prototype}"
SNIPPET_SRC="${ROOT}/kissne-prototype/deploy/nginx-kissne-location.conf"
SNIPPET_DEST="${KISSNE_NGINX_SNIPPET:-/etc/nginx/snippets/kissne-prototype.conf}"

if [[ ! -f "${SRC}/index.html" ]]; then
  echo "ERROR: prototype index not found: ${SRC}/index.html" >&2
  exit 2
fi

echo "[1/5] Stage prototype -> ${DEST}"
sudo install -d -m 0755 "${DEST}"
sudo rsync -a --delete   --exclude '.DS_Store'   --exclude 'deploy/'   "${SRC}/" "${DEST}/"
sudo find "${DEST}" -type d -exec chmod 0755 {} +
sudo find "${DEST}" -type f -exec chmod 0644 {} +

echo "[2/5] Install nginx location snippet -> ${SNIPPET_DEST}"
sudo install -D -m 0644 "${SNIPPET_SRC}" "${SNIPPET_DEST}"

echo "[3/5] Check whether the existing yeqingxu.cyou vhost includes the snippet"
if sudo nginx -T 2>/dev/null | grep -Fq "alias /var/www/kissne-prototype/;"; then
  echo "OK: nginx already loads the Kissne location."
else
  cat >&2 <<EOF
ACTION REQUIRED ONCE:
Add this line INSIDE the existing HTTPS server block for yeqingxu.cyou:

    include ${SNIPPET_DEST};

Do not create another server { } block and do not change the existing
/mobile/pair /mobile/bootstrap /mobile/messages /mobile/cancel proxy locations.

Then run this script again.
EOF
  exit 3
fi

echo "[4/5] Validate and reload nginx"
sudo nginx -t
sudo systemctl reload nginx

echo "[5/5] Verify same-origin UI and API surface"
curl -fsS -o /dev/null -w 'UI /kissne/: %{http_code}\n'   https://yeqingxu.cyou/kissne/

# Token endpoints should be reachable on the SAME origin and reject unauthenticated
# access with 401. /pair is POST-only; GET may be 405 and that is acceptable here.
for path in mobile/bootstrap mobile/messages mobile/cancel; do
  code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST     -H 'Content-Type: application/json' -d '{}'     "https://yeqingxu.cyou/${path}")"
  printf 'API /%s unauthenticated: %s\n' "${path}" "${code}"
  if [[ "${code}" != "401" ]]; then
    echo "ERROR: /${path} expected 401, got ${code}" >&2
    exit 4
  fi
done

echo
echo "READY: https://yeqingxu.cyou/kissne/"
