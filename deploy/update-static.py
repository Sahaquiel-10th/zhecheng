#!/usr/bin/env python3
"""Publish this catalog by atomically switching its current link; never reload Nginx."""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit
import fcntl
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

DOMAIN = 'zhecheng.aiarrival.cn'
SITE = Path('/var/www') / DOMAIN
OTHER_HOSTS = ['agent.aiarrival.cn', 'www.aiarrival.cn', 'town.aiarrival.cn', 's-api.aiarrival.cn', 'theone.aiarrival.cn']


def current_release(site):
    if site.is_symlink() or not site.is_dir() or (site/'releases').is_symlink():
        raise ValueError('本项目目录结构不符合预期。')
    current = site/'current'
    if not current.is_symlink():
        raise ValueError('current 不是软链接，停止以避免覆盖目录。')
    target = current.resolve(strict=True)
    if target.parent != (site/'releases').resolve() or not target.is_dir():
        raise ValueError('current 未指向本项目的独立版本目录。')
    return target


def prepare_release(archive, site):
    current_release(site)
    files = {}
    names = set()
    with tarfile.open(archive, 'r:gz') as package:
        for member in package.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError('部署包包含非法路径或链接。')
            name = str(path)
            if name in names:
                raise ValueError('部署包包含重复路径。')
            names.add(name)
            if member.isfile():
                files[name] = package.extractfile(member).read()
    required = {'index.html', 'app.js', 'styles.css', 'products.js', 'client-theme.css'}
    if not required.issubset(files):
        raise ValueError('部署包缺少必要的页面文件。')

    class References(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key not in ('src', 'href') or not value:
                    continue
                url = urlsplit(value)
                if not url.scheme and not url.netloc and url.path not in ('', '.', './'):
                    if url.path.lstrip('/') not in files:
                        raise ValueError('HTML 引用的文件缺失：' + url.path)
    References().feed(files['index.html'].decode('utf-8'))

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    release = Path(tempfile.mkdtemp(prefix=stamp+'-', dir=site/'releases'))
    for name, data in files.items():
        target = release/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o644)
    for directory in [release, *(p for p in release.rglob('*') if p.is_dir())]:
        directory.chmod(0o755)
    return release.resolve()


def atomic_switch(site, target, expected):
    if current_release(site) != expected.resolve():
        raise ValueError('当前版本已被其他操作更改，停止切换。')
    if target.resolve().parent != (site/'releases').resolve():
        raise ValueError('目标版本不属于本项目。')
    temporary = site/('.current-'+uuid.uuid4().hex)
    try:
        temporary.symlink_to(target)
        os.replace(temporary, site/'current')
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def publish_release(site, release, verify, postcheck):
    previous = current_release(site)
    atomic_switch(site, release, previous)
    try:
        verify(release)
        postcheck()
    except Exception:
        atomic_switch(site, previous, release)
        raise
    return previous


def curl(url, host, port, address='127.0.0.1', headers=False):
    command = ['curl', '--noproxy', '*', '--silent', '--show-error', '--http1.1',
               '--connect-timeout', '2', '--max-time', '5', '--resolve', f'{host}:{port}:{address}']
    if headers:
        command += ['--fail', '--include', '--header', 'Cache-Control: no-cache']
    else:
        command += ['--output', '/dev/null', '--write-out', '%{http_code}']
    result = subprocess.run(command+[url], capture_output=True, check=True)
    return result.stdout


def response_file(path, revision):
    response = curl(f'https://{DOMAIN}/{quote(path)}?release={quote(revision)}', DOMAIN, 443, headers=True)
    header, separator, body = response.partition(b'\r\n\r\n')
    if not separator:
        raise ValueError('HTTPS 响应格式异常。')
    return header, body


def verify_release(release):
    expected = (release/'index.html').read_bytes()
    for attempt in range(12):
        try:
            header, body = response_file('index.html', release.name)
            if b'x-zhecheng-site: catalog' in header.lower() and body == expected:
                break
        except (subprocess.CalledProcessError, ValueError):
            pass
        if attempt == 11:
            raise ValueError('新页面 HTTPS 验收未通过。')
        time.sleep(1)
    checked = 1
    for path in sorted(release.rglob('*')):
        if not path.is_file() or path == release/'index.html':
            continue
        _, body = response_file(path.relative_to(release).as_posix(), release.name)
        if sha256(body).digest() != sha256(path.read_bytes()).digest():
            raise ValueError('线上资源内容与版本不一致：'+path.relative_to(release).as_posix())
        checked += 1
    print(f'HTTPS 页面及 {checked-1} 个资源逐一校验通过。', flush=True)


def existing_snapshot():
    result = {}
    for host in OTHER_HOSTS:
        result[host] = curl(f'https://{host}/', host, 443).decode()
    for family, address in [('ipv4', '127.0.0.1'), ('ipv6', '[::1]')]:
        host = 'zhecheng-default-check.invalid'
        raw = subprocess.run(['curl', '--noproxy', '*', '--silent', '--show-error',
            '--max-time', '5', '--resolve', f'{host}:80:{address}', '--include', f'http://{host}/'],
            capture_output=True, check=True).stdout
        head, _, body = raw.partition(b'\r\n\r\n')
        result['default-'+family] = {'status':head.split(b'\r\n',1)[0].decode(), 'body_sha256':sha256(body).hexdigest()}
    return result


def nginx_fingerprint():
    return {str(path):sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path('/etc/nginx').rglob('*')) if path.is_file()}


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise SystemExit('用法：sudo python3 deploy/update-static.py /tmp/本站部署包.tar.gz')
    current_release(SITE)
    with (SITE/'.static-update.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = current_release(SITE)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = Path(tempfile.mkdtemp(prefix='zhecheng-static-'+stamp+'-', dir='/var/backups'))
        backup.chmod(0o700)
        before_config = nginx_fingerprint()
        print('正在准备静态版本；不会修改配置或加载任何服务。', flush=True)
        release = prepare_release(Path(sys.argv[1]), SITE)
        before = existing_snapshot()
        (backup/'previous.json').write_text(json.dumps({'previous':str(previous),'new':str(release),'nginx':before_config}, indent=2))
        (backup/'existing-before.json').write_text(json.dumps(before, indent=2))
        print(f'旧版本完整保留：{previous}\n检查记录：{backup}', flush=True)

        def postcheck():
            after = existing_snapshot()
            (backup/'existing-after.json').write_text(json.dumps(after, indent=2))
            if before != after or before_config != nginx_fingerprint():
                raise ValueError('其他站点响应或 Nginx 配置指纹出现变化。')

        try:
            publish_release(SITE, release, verify_release, postcheck)
        except Exception:
            print(f'更新未通过。current 当前指向：{current_release(SITE)}；原版本为：{previous}。', file=sys.stderr)
            raise
        print('其他项目状态、默认站点内容及 Nginx 配置指纹前后检查通过。')
        for host in OTHER_HOSTS:
            print(host, before[host])
        print(f'发布成功：https://{DOMAIN}/\n当前版本：{release}\n回退目标：{previous}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        raise SystemExit('部署停止：'+str(exc))
