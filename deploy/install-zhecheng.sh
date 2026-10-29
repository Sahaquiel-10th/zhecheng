#!/usr/bin/env bash
# Initial install or verified recovery after rollback. Changes only this new vhost.
set -Eeuo pipefail
umask 022

domain='zhecheng.aiarrival.cn'
site="/var/www/$domain"
conf="/etc/nginx/sites-enabled/zz-$domain.conf"
archive="${1:-/tmp/zhecheng-web-20261029-v1.tar.gz}"
mode="${2:-initial}"
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config_created=0
reload_attempted=0

fail() { printf '\n停止：%s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail '请使用 sudo bash 运行此脚本。'
[[ -f "$archive" ]] || fail "找不到部署包：$archive"
[[ -f "$script_dir/verify-http.sh" ]] || fail '缺少本次提交配套的验证脚本。'
[[ "$mode" == initial || "$mode" == --resume-after-rollback ]] || fail '不支持的运行模式。'
if [[ "$mode" == initial ]]; then
    [[ ! -e "$site" && ! -L "$site" ]] || fail "目录已存在，未作修改：$site"
else
    [[ -d "$site" && ! -L "$site" && -L "$site/current" ]] || fail '恢复目录结构不符合预期，停止。'
fi
[[ ! -e "$conf" && ! -L "$conf" ]] || fail "配置已存在，未作修改：$conf"
[[ ! -e "/etc/nginx/conf.d/$domain.conf" && ! -L "/etc/nginx/conf.d/$domain.conf" ]] || fail '上次安装的配置文件仍存在，停止。'
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
grep -Eq '^[[:space:]]*include[[:space:]]+/etc/nginx/sites-enabled/\*;' <<< "$active_config" || fail '未找到预期的 sites-enabled 加载位置。'
if grep -Fq -- "$site" <<< "$active_config"; then
    fail '已有 Nginx 配置引用本项目目录，停止以避免覆盖现有用途。'
fi
python3 - "$archive" "$mode" "$site" <<'PY'
import pathlib,sys,tarfile
recover=sys.argv[2]=='--resume-after-rollback'
site=pathlib.Path(sys.argv[3]).resolve()
release=None
if recover:
    release=(site/'current').resolve(strict=True)
    releases=site/'releases'
    if releases.is_symlink() or release.parent != releases or not release.is_dir():
        raise SystemExit('current 不是本项目 releases 下的版本目录，停止。')
with tarfile.open(sys.argv[1], 'r:gz') as t:
    members=t.getmembers()
    names=set()
    for m in members:
        p=pathlib.PurePosixPath(m.name)
        if p.is_absolute() or '..' in p.parts or not (m.isfile() or m.isdir()):
            raise SystemExit('部署包路径或文件类型异常，停止。')
        names.add(str(p))
        if recover and m.isfile():
            disk=release / str(p)
            if not disk.is_file() or disk.resolve() != disk:
                raise SystemExit('恢复文件缺失或包含链接，停止：'+str(p))
            if disk.read_bytes() != t.extractfile(m).read():
                raise SystemExit('保留文件与指定 Git 版本不一致，停止：'+str(p))
    if not {'index.html','app.js','styles.css','products.js'}.issubset(names):
        raise SystemExit('部署包缺少必要文件，停止。')
print('部署包检查通过。')
if recover: print('保留目录中的所有发布文件均与指定 Git 版本一致；本次恢复不改写这些文件。')
PY

stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/var/backups/zhecheng-$stamp-$$"
install -d -m 700 "$backup"
(umask 077; tar -czf "$backup/nginx-before.tar.gz" -C /etc nginx)
printf 'Nginx 备份：%s/nginx-before.tar.gz\n' "$backup"

# Record existing routes for comparison; these requests do not change configuration.
check_existing() {
    local host stage=${1:?}
    for host in agent.aiarrival.cn www.aiarrival.cn town.aiarrival.cn s-api.aiarrival.cn theone.aiarrival.cn; do
        printf '%s ' "$host"
        curl --noproxy '*' --silent --show-error --output /dev/null --max-time 8 \
            --resolve "$host:443:127.0.0.1" --write-out '%{http_code}\n' "https://$host/" || true
    done
    # Unknown hosts must keep reaching the original default site, including IPv6.
    local family address
    for family in ipv4 ipv6; do
        if [[ $family == ipv4 ]]; then address=127.0.0.1; else address='[::1]'; fi
        : > "$backup/default-$stage-$family.html"
        printf 'existing-default-%s ' "$family"
        curl --noproxy '*' --silent --show-error --max-time 3 \
            --resolve "zhecheng-default-check.invalid:80:$address" \
            --output "$backup/default-$stage-$family.html" --write-out '%{http_code}\n' \
            'http://zhecheng-default-check.invalid/' || true
    done
}
check_existing before > "$backup/existing-before.txt" 2>&1

rollback_on_error() {
    local status=$?
    local reverted=1
    trap - ERR
    set +e
    if [[ $config_created -eq 1 ]]; then
        rm -- "$conf" || reverted=0
        if [[ $reload_attempted -eq 1 ]]; then
            if ! (nginx -t && systemctl reload nginx); then reverted=0; fi
        fi
    fi
    if [[ $reverted -eq 1 ]]; then
        printf '\n部署未通过，已撤下本次新建的站点配置；其他配置文件未改动。\n' >&2
    else
        printf '\n部署未通过，自动回退也未完成，请保留输出并检查 Nginx 状态。\n' >&2
    fi
    printf '备份及检查结果：%s\n项目文件保留在：%s\n' "$backup" "$site" >&2
    exit "$status"
}
trap rollback_on_error ERR

if [[ "$mode" == --resume-after-rollback ]]; then
    release=$(readlink -f -- "$site/current")
else
    release="$site/releases/$stamp"
    install -d -m 755 "$release" "$site/acme/.well-known/acme-challenge"
    tar -xzf "$archive" --no-same-owner --no-same-permissions -C "$release"
    find "$release" -type d -exec chmod 755 {} +
    find "$release" -type f -exec chmod 644 {} +
    ln -s "$release" "$site/current"
fi

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
        add_header X-Zhecheng-Site "catalog" always;
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
bash "$script_dir/verify-http.sh" "$release/index.html" "$backup" "$domain"
check_existing after > "$backup/existing-after.txt" 2>&1
if ! cmp -s "$backup/existing-before.txt" "$backup/existing-after.txt"; then
    printf '现有项目加载前后状态出现变化，停止并回退新站配置。\n' >&2
    diff -u "$backup/existing-before.txt" "$backup/existing-after.txt" || true
    false
fi
for family in ipv4 ipv6; do
    if ! cmp -s "$backup/default-before-$family.html" "$backup/default-after-$family.html"; then
        printf '现有默认站点返回内容发生变化（%s），停止并回退新站配置。\n' "$family" >&2
        false
    fi
done
trap - ERR
printf '\n新站本机访问验证通过。现有项目加载前后状态如下：\n'
printf '\n加载前：\n'
cat "$backup/existing-before.txt"
printf '\n加载后：\n'
cat "$backup/existing-after.txt"
printf '\n独立配置：%s\n独立目录：%s\n' "$conf" "$site"
printf 'HTTP 站点已就绪；DNS、公网访问与 HTTPS 证书仍需分别验证。\n'
