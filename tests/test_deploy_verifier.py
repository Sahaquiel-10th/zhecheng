"""Regression: bypass proxy settings and wait for a graceful reload without accepting a fallback site."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import os, subprocess, threading, unittest

VERIFIER = Path(__file__).resolve().parents[1] / 'deploy/verify-http.sh'
EXPECTED = b'<!doctype html><title>catalog</title>'

class VerifyHTTPTest(unittest.TestCase):
    def run_case(self, old_requests, wrong_body=False):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(self.headers.get('Host'))
                ready = len(calls) > old_requests
                self.send_response(200)
                if ready: self.send_header('X-Zhecheng-Site', 'catalog')
                self.end_headers()
                self.wfile.write(EXPECTED if ready and not wrong_body else b'<title>other project</title>')
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as d:
                expected = Path(d) / 'expected.html'
                expected.write_bytes(EXPECTED)
                env = dict(os.environ, http_proxy='http://127.0.0.1:1', HTTP_PROXY='http://127.0.0.1:1', ALL_PROXY='http://127.0.0.1:1', all_proxy='http://127.0.0.1:1', no_proxy='', NO_PROXY='')
                result = subprocess.run(['bash',str(VERIFIER),str(expected),d,'zhecheng.aiarrival.cn',str(server.server_port),'4','0.01'], env=env, capture_output=True, text=True, timeout=10)
                return result, calls
        finally:
            server.shutdown()
            server.server_close()
    def test_delayed_reload_and_proxy_bypass(self):
        result, calls = self.run_case(2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(h.startswith('zhecheng.aiarrival.cn:') for h in calls))
    def test_fallback_site_never_passes(self):
        result, calls = self.run_case(99)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 4)
    def test_correct_header_with_wrong_html_never_passes(self):
        result, calls = self.run_case(0, wrong_body=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 4)

if __name__ == '__main__': unittest.main()
