import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('static_update', Path(__file__).resolve().parents[1]/'deploy/update-static.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class StaticUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name).resolve()/'site'
        self.old = self.site/'releases/old'
        self.old.mkdir(parents=True)
        (self.old/'index.html').write_text('old')
        (self.site/'current').symlink_to(self.old)
        self.files = {name:b'' for name in ('app.js','styles.css','products.js','client-theme.css')}
        self.files['index.html'] = b'<script src="app.js"></script><img src="assets/logo.png">'
        self.files['assets/logo.png'] = b'logo'

    def package(self, extra=None):
        archive = Path(self.temp.name)/'package.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for name, data in self.files.items():
                item = tarfile.TarInfo(name)
                item.size = len(data)
                tar.addfile(item, io.BytesIO(data))
            if extra:
                tar.addfile(extra)
        return archive

    def prepare(self):
        return updater.prepare_release(self.package(), self.site)

    def test_success_keeps_old_release(self):
        release = self.prepare()
        observed = []
        updater.publish_release(self.site, release, lambda target: observed.append(target), lambda: None)
        self.assertEqual(updater.current_release(self.site), release)
        self.assertEqual(observed, [release])
        self.assertEqual((self.old/'index.html').read_text(), 'old')
        self.assertEqual((release/'assets/logo.png').read_bytes(), b'logo')

    def test_failed_verification_restores_previous_link(self):
        release = self.prepare()
        def fail(_):
            raise ValueError('wrong page')
        with self.assertRaisesRegex(ValueError, 'wrong page'):
            updater.publish_release(self.site, release, fail, lambda: None)
        self.assertEqual(updater.current_release(self.site), self.old)

    def test_failed_other_site_check_restores_previous_link(self):
        release = self.prepare()
        def fail():
            raise ValueError('other site changed')
        with self.assertRaisesRegex(ValueError, 'other site changed'):
            updater.publish_release(self.site, release, lambda _: None, fail)
        self.assertEqual(updater.current_release(self.site), self.old)

    def test_rejects_archive_traversal_and_links(self):
        for name, type_ in [('../outside', tarfile.REGTYPE), ('/outside', tarfile.REGTYPE), ('assets/link', tarfile.SYMTYPE)]:
            with self.subTest(name=name):
                member = tarfile.TarInfo(name)
                member.type = type_
                member.linkname = '/etc/nginx'
                with self.assertRaises(ValueError):
                    updater.prepare_release(self.package(member), self.site)
                self.assertEqual(updater.current_release(self.site), self.old)

    def test_missing_html_asset_stops_before_switch(self):
        del self.files['assets/logo.png']
        with self.assertRaisesRegex(ValueError, '引用的文件缺失'):
            self.prepare()
        self.assertEqual(updater.current_release(self.site), self.old)

    def test_refuses_targets_outside_site_and_concurrent_change(self):
        release = self.prepare()
        with self.assertRaisesRegex(ValueError, '不属于本项目'):
            updater.atomic_switch(self.site, Path(self.temp.name), self.old)
        updater.atomic_switch(self.site, release, self.old)
        with self.assertRaisesRegex(ValueError, '其他操作更改'):
            updater.atomic_switch(self.site, self.old, self.old)
        self.assertEqual(updater.current_release(self.site), release)


if __name__ == '__main__':
    unittest.main()
