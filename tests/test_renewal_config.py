from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_renewal', ROOT/'deploy/check-renewal.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
FIXTURE = (ROOT/'tests/fixtures/certbot-5.8-renewal.conf').read_text()
HOOK = '/usr/local/libexec/zhecheng/renew-nginx.sh'


class RenewalConfigTest(unittest.TestCase):
    def test_certbot_root_keys_and_nested_webroot_map(self):
        checker.validate(FIXTURE, HOOK)

    def test_quoted_deploy_hook_alias(self):
        checker.validate(FIXTURE.replace('renew_hook = '+HOOK, 'deploy_hook = "'+HOOK+'" # saved hook'), HOOK)

    def test_other_project_hook_is_rejected(self):
        with self.assertRaises(ValueError):
            checker.validate(FIXTURE.replace(HOOK, '/usr/local/libexec/other-project/hook.sh'), HOOK)

    def test_hook_command_containing_expected_path_is_rejected(self):
        with self.assertRaises(ValueError):
            checker.validate(FIXTURE.replace(HOOK, HOOK+'; echo unexpected'), HOOK)

    def test_nested_or_root_fields_cannot_satisfy_renewal_parameters(self):
        with self.assertRaises(ValueError):
            checker.validate('authenticator = webroot\nrenew_hook = '+HOOK+'\n[renewalparams]\n[[webroot_map]]\nauthenticator = webroot\nrenew_hook = '+HOOK, HOOK)

    def test_wrong_authenticator_is_rejected(self):
        with self.assertRaises(ValueError):
            checker.validate(FIXTURE.replace('authenticator = webroot', 'authenticator = standalone'), HOOK)


if __name__ == '__main__': unittest.main()
