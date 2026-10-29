#!/usr/bin/env bash
# Initial install only. Creates one new vhost and one new static site directory.
set -Eeuo pipefail
umask 022

domain='zhecheng.aiarrival.cn'
site="/var/www/$domain"
conf="/etc/nginx/conf.d/$domain.conf"
archive="${1:-/tmp/zhecheng-web-20261029-v1.tar.gz}"
config_created=0
reload_attempted=0

fail() { printf '\n停止：%s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail '请使用 sudo bash 运行此脚本。'
[[ -f "$archive" ]] || fail "找不到部署包：$archive"
[[ ! -e "$site" && ! -L "$site" ]] || fail "目录已存在，未作修改：$site"
[[ ! -e "$conf" && ! -L "$conf" ]] || fail "配置已存在，未作修改：$conf"
command -v python3 >/dev/null || fail '缺少 python3。'
command -v curl >/dev/null || fail '缺少 curl。'
nginx -t || fail '现有 Nginx 检查未通过。'
active_config=$(nginx -T 2>/dev/null)
if printf '%s\n' "$active_config" | python3 -c '
import re,sys
text = re.sub(r"#.*", "", sys.stdin.read())
names = [n for group in re.findall(r"\bserver_name\s+([^;]+);", text) for n in group.split()]
sys.exit(0 if "zhecheng.aiarrival.cn" in names else 1)
'; then
    fail '已经存在同域名站点，未作修改。'
fi
grep -Eq '^[[:space:]]*include[[:space:]]+/etc/nginx/conf\.d/\*\.conf;' <<< "$active_config" || fail '未找到预期的 conf.d 加载位置。'
python3 - "$archive" <<'PY'
import pathlib,sys,tarfile
with tarfile.open(sys.argv[1], 'r:gz') as t:
    members=t.getmembers()
    names=set()
    for m in members:
        p=pathlib.PurePosixPath(m.name)
        if p.is_absolute() or '..' in p.parts or not (m.isfile() or m.isdir()):
            raise SystemExit('部署包路径或文件类型异常，停止。')
        names.add(str(p))
    if not {'index.html','app.js','styles.css','products.js'}.issubset(names):
        raise SystemExit('部署包缺少必要文件，停止。')
print('部署包检查通过。')
PY

stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/var/backups/zhecheng-$stamp-$$"
install -d -m 700 "$backup"
(umask 077; tar -czf "$backup/nginx-before.tar.gz" -C /etc nginx)
printf 'Nginx 备份：%s/nginx-before.tar.gz\n' "$backup"

# Record existing routes for comparison; these requests do not change configuration.
check_existing() {
    local host
    for host in agent.aiarrival.cn www.aiarrival.cn town.aiarrival.cn s-api.aiarrival.cn theone.aiarrival.cn; do
        printf '%s ' "$host"
        curl --silent --show-error --output /dev/null --max-time 12 \
            --resolve "$host:443:127.0.0.1" --write-out '%{http_code}\n' "https://$host/" || true
    done
}
check_existing > "$backup/existing-before.txt" 2>&1

rollback_on_error() {
    local status=$?
    trap - ERR
    set +e
    if [[ $config_created -eq 1 ]]; then
        rm -- "$conf"
        if [[ $reload_attempted -eq 1 ]]; then
            nginx -t && systemctl reload nginx
        fi
    fi
    printf '\n部署未通过，已撤下本次新建的站点配置；其他配置文件未改动。\n' >&2
    printf '备份及检查结果：%s\n项目文件保留在：%s\n' "$backup" "$site" >&2
    exit "$status"
}
trap rollback_on_error ERR

release="$site/releases/$stamp"
install -d -m 755 "$release" "$site/acme/.well-known/acme-challenge"
tar -xzf "$archive" --no-same-owner --no-same-permissions -C "$release"
find "$release" -type d -exec chmod 755 {} +
find "$release" -type f -exec chmod 644 {} +
ln -s "$release" "$site/current"

# noclobber refuses to replace a file that appeared after the preflight check.
set -o noclobber
cat > "$conf" <<'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name zhecheng.aiarrival.cn;
    root /var/www/zhecheng.aiarrival.cn/current;
    index index.html;
    charset utf-8;
    access_log /var/log/nginx/zhecheng.aiarrival.cn.access.log;
    error_log /var/log/nginx/zhecheng.aiarrival.cn.error.log;
    add_header X-Content-Type-Options nosniff always;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/zhecheng.aiarrival.cn/acme;
        default_type text/plain;
        try_files $uri =404;
    }
    location / {
        try_files $uri $uri/ =404;
        add_header Cache-Control "no-cache";
    }
    location /assets/ {
        try_files $uri =404;
        expires 1h;
    }
    location ~ /\. { deny all; }
}
NGINX
set +o noclobber
config_created=1
nginx -t
reload_attempted=1
systemctl reload nginx
curl --fail --silent --show-error --max-time 15 \
    --resolve "$domain:80:127.0.0.1" "http://$domain/" -o "$backup/new-site-response.html"
cmp "$release/index.html" "$backup/new-site-response.html"
check_existing > "$backup/existing-after.txt" 2>&1
trap - ERR
printf '\n新站本机访问验证通过。现有项目加载前后状态如下：\n'
printf '\n加载前：\n'
cat "$backup/existing-before.txt"
printf '\n加载后：\n'
cat "$backup/existing-after.txt"
printf '\n独立配置：%s\n独立目录：%s\n' "$conf" "$site"
printf 'HTTP 站点已就绪；DNS、公网访问与 HTTPS 证书仍需分别验证。\n'
