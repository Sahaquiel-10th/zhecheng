"""Read only our known Certbot hook fields; accept ConfigObj root keys and nested sections."""
from pathlib import Path
import shlex
import sys


def renewal_parameters(text):
    parameters = {}
    in_parameters = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('['):
            in_parameters = line.split('#', 1)[0].strip() == '[renewalparams]'
            continue
        if not in_parameters or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if key not in ('authenticator', 'deploy_hook', 'renew_hook'):
            continue
        if key in parameters:
            raise ValueError('续期配置存在重复字段：' + key)
        tokens = shlex.split(value.strip(), comments=True)
        if len(tokens) != 1:
            raise ValueError('续期配置字段不是预期的单一值：' + key)
        parameters[key] = tokens[0]
    return parameters


def validate(text, hook):
    p = renewal_parameters(text)
    hooks = [p[k] for k in ('deploy_hook', 'renew_hook') if k in p]
    if p.get('authenticator') != 'webroot' or not hooks or any(h != hook for h in hooks):
        raise ValueError('持久化的 webroot / deploy hook 设置不符合本项目预期。')


if __name__ == '__main__':
    try:
        validate(Path(sys.argv[1]).read_text(), sys.argv[2])
    except (OSError, ValueError) as exc:
        raise SystemExit('续期设置检查未通过：' + str(exc))
    print('Certbot 续期设置检查通过（webroot 与本域名专属 hook）。')
