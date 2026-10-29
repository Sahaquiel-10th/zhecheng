"""Regression: bypass proxy settings and wait for a graceful reload without accepting a fallback site."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import os, ssl, subprocess, threading, unittest

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

    def test_untrusted_https_certificate_is_rejected(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('X-Zhecheng-Site', 'catalog')
                self.end_headers()
                self.wfile.write(EXPECTED)
            def log_message(self, *args): pass
        with TemporaryDirectory() as d:
            root=Path(d)
            key,cert=root/'key.pem',root/'cert.pem'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=zhecheng.aiarrival.cn','-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert,key)
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            server.socket=context.wrap_socket(server.socket,server_side=True)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                expected=root/'expected.html'
                expected.write_bytes(EXPECTED)
                result=subprocess.run(['bash',str(VERIFIER),str(expected),d,'zhecheng.aiarrival.cn',str(server.server_port),'1','0','https'],capture_output=True,text=True,timeout=10)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('certificate',result.stderr.lower())
            finally:
                server.shutdown()
                server.server_close()

    def test_renewal_hook_ignores_other_certificates(self):
        hook=VERIFIER.parent/'renew-nginx.sh'
        for values in [{},{'RENEWED_LINEAGE':'/etc/letsencrypt/live/theone.aiarrival.cn','RENEWED_DOMAINS':'theone.aiarrival.cn'},{'RENEWED_LINEAGE':'/etc/letsencrypt/live/zhecheng.aiarrival.cn','RENEWED_DOMAINS':'theone.aiarrival.cn'}]:
            env=dict(os.environ)
            env.pop('RENEWED_LINEAGE',None)
            env.pop('RENEWED_DOMAINS',None)
            env.update(values)
            result=subprocess.run(['sh',str(hook)],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'')

if __name__ == '__main__': unittest.main()
