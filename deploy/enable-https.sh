#!/usr/bin/env bash
# Obtain one webroot certificate; replace only this project's vhost; verify and renew it.
set -Eeuo pipefail
umask 022
domain=zhecheng.aiarrival.cn
site="/var/www/$domain"
conf="/etc/nginx/sites-enabled/zz-$domain.conf"
cert="/etc/letsencrypt/live/$domain"
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
hook=/usr/local/libexec/zhecheng/renew-nginx.sh
changed=0
reloaded=0
probe=''
staged=''
fail() { printf '\n停止：%s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail '请使用 sudo bash 执行。'
[[ -f "$conf" && ! -L "$conf" && -f "$site/current/index.html" ]] || fail '没有找到已部署的独立站点。'
[[ -x /snap/bin/certbot ]] || fail '没有找到预期的 /snap/bin/certbot。'
nginx -t
# Refuse to replace a manually changed or unrelated configuration.
python3 - "$conf" "$script_dir" <<'PY'
from pathlib import Path
import re,sys
normalize=lambda s:re.sub(r'#[^\n]*','',s).split()
actual=normalize(Path(sys.argv[1]).read_text())
base=Path(sys.argv[2])
if not any(actual==normalize((base/name).read_text()) for name in ['zhecheng.aiarrival.cn.http.conf','zhecheng.aiarrival.cn.https.conf']):
    raise SystemExit('站点配置与已知模板不一致，停止，未修改任何站点。')
PY
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/var/backups/zhecheng-https-$stamp-$$"
install -d -m 700 "$backup"
(umask 077; tar -czf "$backup/nginx-before.tar.gz" -C /etc nginx)
cp -p -- "$conf" "$backup/site-before.conf"
printf '备份：%s\n' "$backup"
trap '[[ -z "$probe" ]] || rm -f -- "$probe"; [[ -z "$staged" ]] || rm -f -- "$staged"' EXIT

check_existing() {
    local stage=$1 host family address
    for host in agent.aiarrival.cn www.aiarrival.cn town.aiarrival.cn s-api.aiarrival.cn theone.aiarrival.cn; do
        printf '%s ' "$host"
        curl --noproxy '*' -sS -o /dev/null --max-time 8 --resolve "$host:443:127.0.0.1" -w '%{http_code}\n' "https://$host/" || true
    done
    # Check known HTTPS sites and the original HTTP defaults for both families.
    for family in ipv4 ipv6; do
        if [[ $family == ipv4 ]]; then address=127.0.0.1; else address='[::1]'; fi
        : > "$backup/default-$stage-$family.html"
        printf 'existing-default-%s ' "$family"
        curl --noproxy '*' -sS --max-time 3 --resolve "zhecheng-default-check.invalid:80:$address" \
            -o "$backup/default-$stage-$family.html" -w '%{http_code}\n' 'http://zhecheng-default-check.invalid/' || true
    done
}
check_existing before > "$backup/existing-before.txt" 2>&1

# Verify the public ACME webroot before contacting the certificate authority.
token="zhecheng-check-$(openssl rand -hex 12)"
probe="$site/acme/.well-known/acme-challenge/$token"
(set -o noclobber; printf '%s' "$token" > "$probe")
curl --noproxy '*' --fail -sS --max-time 15 "http://$domain/.well-known/acme-challenge/$token" -o "$backup/acme-probe.txt"
cmp "$probe" "$backup/acme-probe.txt"
rm -- "$probe"
probe=''

# Install only our own lineage-scoped hook. Never replace an unknown file.
if [[ -e "$hook" || -L "$hook" ]]; then
    [[ ! -L "$hook" ]] && cmp -s "$script_dir/renew-nginx.sh" "$hook" || fail '续期 hook 已存在且内容不同。'
else
    install -d -m 755 "$(dirname -- "$hook")"
    install -m 755 "$script_dir/renew-nginx.sh" "$hook"
fi
if [[ -f "$cert/cert.pem" ]]; then
    # Never change an existing certificate that also covers other projects.
    python3 - "$cert/cert.pem" "$domain" <<'PY'
import re,subprocess,sys
san=subprocess.check_output(['openssl','x509','-in',sys.argv[1],'-noout','-ext','subjectAltName'],text=True)
if re.findall(r'DNS:([^,\s]+)',san)!=[sys.argv[2]]:
    raise SystemExit('已有同名证书包含其他域名，停止。')
PY
fi
if [[ -f "$cert/cert.pem" && -f "$cert/fullchain.pem" && -f "$cert/privkey.pem" ]] \
    && openssl x509 -in "$cert/cert.pem" -noout -checkend 86400 >/dev/null; then
    python3 "$script_dir/check-renewal.py" "/etc/letsencrypt/renewal/$domain.conf" "$hook"
    printf '复用已经签发的有效证书，本次不执行证书签发请求。\n'
else
    /snap/bin/certbot certonly --non-interactive --webroot \
        --webroot-path "$site/acme" --cert-name "$domain" -d "$domain" \
        --keep-until-expiring --no-directory-hooks --deploy-hook "$hook"
fi
openssl x509 -in "$cert/cert.pem" -noout -checkhost "$domain"
openssl x509 -in "$cert/cert.pem" -noout -checkend 86400
python3 "$script_dir/check-renewal.py" "/etc/letsencrypt/renewal/$domain.conf" "$hook"

rollback() {
    local status=$? reverted=1
    trap - ERR
    set +e
    if [[ $changed -eq 1 ]]; then
        staged=$(mktemp /etc/nginx/sites-enabled/.zhecheng-restore.XXXXXX)
        if [[ -n "$staged" ]] && cp -p -- "$backup/site-before.conf" "$staged" && mv -f -- "$staged" "$conf"; then
            staged=''
        else
            reverted=0
        fi
        if [[ $reloaded -eq 1 ]]; then
            if ! (nginx -t && systemctl reload nginx); then reverted=0; fi
        fi
    fi
    if [[ $reverted -eq 1 ]]; then
        printf '\nHTTPS 配置验收失败，已恢复本项目之前的站点配置；备份：%s\n' "$backup" >&2
    else
        printf '\nHTTPS 配置验收及自动回退未全部完成，请检查输出。备份：%s\n' "$backup" >&2
    fi
    exit "$status"
}
trap rollback ERR
staged=$(mktemp /etc/nginx/sites-enabled/.zhecheng-https.XXXXXX)
install -m 644 "$script_dir/zhecheng.aiarrival.cn.https.conf" "$staged"
changed=1
mv -f -- "$staged" "$conf"
staged=''
nginx -t
reloaded=1
systemctl reload nginx
bash "$script_dir/verify-http.sh" "$site/current/index.html" "$backup" "$domain" 443 12 1 https
curl --noproxy '*' -sS --max-time 8 --resolve "$domain:80:127.0.0.1" \
    -D "$backup/redirect.headers" -o /dev/null "http://$domain/"
grep -iq '^Location: https://zhecheng.aiarrival.cn/' "$backup/redirect.headers"
check_existing after > "$backup/existing-after.txt" 2>&1
cmp "$backup/existing-before.txt" "$backup/existing-after.txt"
for family in ipv4 ipv6; do
    cmp "$backup/default-before-$family.html" "$backup/default-after-$family.html"
done
trap - ERR
printf '\nHTTPS、HTTP 跳转和其他站点前后对比通过。\n'
cat "$backup/existing-after.txt"

# Test only this lineage, including its deploy hook, using the staging CA.
if [[ -e /var/lib/zhecheng-certbot/last-reload.ok ]]; then
    mv -- /var/lib/zhecheng-certbot/last-reload.ok "$backup/reload-marker-before.txt"
fi
if ! /snap/bin/certbot renew --cert-name "$domain" --dry-run --run-deploy-hooks --no-directory-hooks; then
    fail 'HTTPS 已开通，但续期演练未通过；请保留输出，不要重复申请证书。'
fi
[[ -s /var/lib/zhecheng-certbot/last-reload.ok ]] || fail 'HTTPS 已开通，但续期演练后的 Nginx 加载 hook 未确认成功。'
timer=''
for candidate in snap.certbot.renew.timer certbot.timer zhecheng-cert-renew.timer; do
    if systemctl is-active --quiet "$candidate" && systemctl is-enabled --quiet "$candidate"; then timer=$candidate; break; fi
done
if [[ -z "$timer" ]]; then
    for name in zhecheng-cert-renew.service zhecheng-cert-renew.timer; do
        target="/etc/systemd/system/$name"
        if [[ -e "$target" || -L "$target" ]]; then
            [[ ! -L "$target" ]] && cmp -s "$script_dir/$name" "$target" || fail "定时任务文件已存在且不同：$target"
        else
            install -m 644 "$script_dir/$name" "$target"
        fi
    done
    systemctl daemon-reload
    systemctl enable --now zhecheng-cert-renew.timer
    timer=zhecheng-cert-renew.timer
fi
systemctl is-active "$timer"
systemctl is-enabled "$timer"
systemctl list-timers --all "$timer" --no-pager
printf '\nHTTPS 已开通，单域名续期演练通过。自动续期使用：%s\n' "$timer"
printf '链接：https://%s/\n' "$domain"
