#!/usr/bin/env bash
# Wait for a graceful Nginx reload; never accept another site's successful HTTP response.
set -euo pipefail
expected=${1:?expected HTML required}
output=${2:?diagnostic directory required}
domain=${3:?domain required}
port=${4:-80}
attempts=${5:-12}
delay=${6:-1}
[[ -f "$expected" && -d "$output" ]] || exit 2
[[ "$port" =~ ^[0-9]+$ && "$attempts" =~ ^[0-9]+$ ]] || exit 2
for ((attempt=1; attempt<=attempts; attempt++)); do
    if curl --noproxy '*' --fail --silent --show-error \
        --connect-timeout 2 --max-time 3 --http1.1 \
        --resolve "$domain:$port:127.0.0.1" \
        --header 'Connection: close' \
        --dump-header "$output/new-site-response.headers" \
        "http://$domain:$port/?deploy-check=$attempt" \
        -o "$output/new-site-response.html" 2> "$output/new-site-curl.error" \
        && grep -iq '^X-Zhecheng-Site: catalog' "$output/new-site-response.headers" \
        && cmp -s "$expected" "$output/new-site-response.html"; then
        printf '新站专属响应头及完整 HTML 一致，验收通过（第 %s 次）。\n' "$attempt"
        exit 0
    fi
    if [[ $attempt -lt $attempts ]]; then sleep "$delay"; fi
done
printf '直连本机验收连续 %s 次未通过；保留响应头、响应正文及 curl 错误供检查。\n' "$attempts" >&2
cat "$output/new-site-curl.error" >&2
exit 1
