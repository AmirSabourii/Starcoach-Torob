"""Bootstrap data loader (used only when the DB is missing on the disk).
Serves on $PORT until the required data files exist in $DATA_DIR, then exits so start.sh can launch the app.
Upload (token-protected, chunked so it passes ingress body-size limits):
  PUT /__upload/<name>?token=<PLAYGROUND_TOKEN>&offset=<bytes>   body = chunk
  GET /__status?token=...                                          -> sizes on disk
  POST /__done?token=...                                           -> gunzip torob.sqlite.gz if needed, then exit
"""
import gzip, hmac, json, os, shutil, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
DATA = os.environ.get('DATA_DIR', '/data'); TOK = os.environ.get('PLAYGROUND_TOKEN', '')
ALLOWED = {'torob.sqlite.gz', 'torob.sqlite', 'product_emb.f16.npy', 'product_emb_ids.json'}

class H(BaseHTTPRequestHandler):
    def _ok(self, q):
        return bool(TOK) and hmac.compare_digest(q.get('token', [''])[0], TOK)
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code)
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass        # never log query strings (token)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == '/__status' and self._ok(q):
            return self._send(200, {f: os.path.getsize(os.path.join(DATA, f)) for f in ALLOWED if os.path.exists(os.path.join(DATA, f))})
        self._send(503, {'status': 'loading data'})
    def do_PUT(self):
        u = urlparse(self.path); q = parse_qs(u.query); name = os.path.basename(u.path)
        if not (u.path.startswith('/__upload/') and name in ALLOWED and self._ok(q)): return self._send(403, {'err': 'forbidden'})
        off = int(q.get('offset', ['0'])[0]); n = int(self.headers.get('Content-Length', '0'))
        p = os.path.join(DATA, name + '.part'); cur = os.path.getsize(p) if os.path.exists(p) else 0
        if off != cur: return self._send(409, {'err': 'offset mismatch', 'have': cur})
        with open(p, 'ab') as f:
            left = n
            while left:
                b = self.rfile.read(min(left, 1 << 20))
                if not b: break
                f.write(b); left -= len(b)
        self._send(200, {'have': os.path.getsize(p)})
    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path != '/__done' or not self._ok(q): return self._send(403, {'err': 'forbidden'})
        for f in ALLOWED:
            p = os.path.join(DATA, f + '.part')
            if os.path.exists(p): os.replace(p, os.path.join(DATA, f))
        gz = os.path.join(DATA, 'torob.sqlite.gz'); db = os.path.join(DATA, 'torob.sqlite')
        if os.path.exists(gz) and not os.path.exists(db):
            with gzip.open(gz, 'rb') as i, open(db + '.tmp', 'wb') as o: shutil.copyfileobj(i, o, 1 << 20)
            os.replace(db + '.tmp', db)
        self._send(200, {'ok': True, 'files': {f: os.path.getsize(os.path.join(DATA, f)) for f in ALLOWED if os.path.exists(os.path.join(DATA, f))}})
        if os.path.exists(db): os._exit(0)

if __name__ == '__main__':
    os.makedirs(DATA, exist_ok=True)
    print(f'[loader] DB missing in {DATA}; waiting for chunked upload on port {os.environ.get("PORT", "8000")}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8000'))), H).serve_forever()
