#!/bin/sh
# Stored as this certificate's deploy hook, outside global hook directories.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
lineage=${RENEWED_LINEAGE:-}
[ "${lineage%/}" = '/etc/letsencrypt/live/zhecheng.aiarrival.cn' ] || exit 0
[ "${RENEWED_DOMAINS:-}" = 'zhecheng.aiarrival.cn' ] || exit 0
conf=/etc/nginx/sites-enabled/zz-zhecheng.aiarrival.cn.conf
# Initial issuance precedes the HTTPS configuration, so no reload is needed yet.
grep -Fq 'ssl_certificate /etc/letsencrypt/live/zhecheng.aiarrival.cn/fullchain.pem;' "$conf" || exit 0
nginx -t
systemctl reload nginx
umask 077
install -d -m 700 /var/lib/zhecheng-certbot
marker=$(mktemp /var/lib/zhecheng-certbot/reload.XXXXXX)
date -u +%Y-%m-%dT%H:%M:%SZ > "$marker"
mv -f -- "$marker" /var/lib/zhecheng-certbot/last-reload.ok
printf 'zhecheng.aiarrival.cn: renewed certificate loaded via graceful Nginx reload\n'
