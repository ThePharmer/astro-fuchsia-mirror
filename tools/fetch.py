import os, ssl, urllib.request, concurrent.futures as cf, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from far import merkle_root
BASE = "https://fuchsia-blobs.googleusercontent.com/"
CA = "/root/.ccr/ca-bundle.crt"
CTX = ssl.create_default_context(cafile=CA) if os.path.exists(CA) else ssl.create_default_context()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler(), urllib.request.HTTPSHandler(context=CTX))

def _req(url, method="GET", headers=None, tries=4):
    for i in range(tries):
        try:
            r = OPENER.open(urllib.request.Request(url, method=method, headers=headers or {}), timeout=60)
            return r.status, dict(r.headers), (r.read() if method == "GET" else b"")
        except urllib.error.HTTPError as e:
            if e.code in (404, 403, 410, 416): return e.code, {}, b""   # 416: server rejects Range on tiny blobs; caller falls back
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return -1, {}, b""

def get_blob(m, cache):
    """Full download, merkle-verified, cached. Returns bytes or None."""
    p = os.path.join(cache, m)
    if os.path.exists(p):
        return open(p, "rb").read()
    st, _, b = _req(BASE + m)
    if st != 200 or merkle_root(b) != m:
        return None
    with open(p + ".tmp", "wb") as f: f.write(b)
    os.replace(p + ".tmp", p)
    return b

def head(m):
    st, h, _ = _req(BASE + m, method="HEAD")
    return st, int(h.get("Content-Length", h.get("content-length", -1)) or -1)

def range_get(m, n=4096):
    st, h, b = _req(BASE + m, headers={"Range": f"bytes=0-{n-1}"})
    return st, b

def pmap(fn, items, workers=24):
    with cf.ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))
