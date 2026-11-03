"""Fetch helpers for the daily sync. Same rules as pkg_fetch.py and blob_probe.py (which built the original
mirror), packaged as functions that work on a small per-run store."""
import os, sys, json, zlib, hashlib, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from far import parse_far, parse_contents, merkle_root
from fetch import _req, BASE
from store import is_text, put_text, printable_strings, RESTRICTED, TEXT_MAX

TUF = "https://a3i1gkkxw4t8hleigzvg15pn8.fuchsia-updates.googleusercontent.com/"


def tuf_get(path):
    st, _, b = _req(TUF + path)
    return st, b


def _pkg_work(it):
    m, name = it
    st, _, b = _req(BASE + m)
    if st != 200: return m, name, f"http {st}", 0, None, []
    if merkle_root(b) != m: return m, name, "merkle mismatch", len(b), None, []
    e = parse_far(b)
    restricted = name in RESTRICTED
    entries, texts = [], []
    for path, data in sorted(e.items()):
        ent = {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        keep_text = path in ("meta/package", "meta/contents") or (not restricted and is_text(data))
        if keep_text:
            texts.append(data); ent["text"] = hashlib.sha256(data).hexdigest()
        elif not restricted and path.endswith(".cm"):
            s = printable_strings(data).encode(); texts.append(s); ent["strings"] = hashlib.sha256(s).hexdigest()
        entries.append(ent)
    rec = {"name": name, "restricted": restricted, "meta_far_size": len(b), "entries": entries,
           "contents": parse_contents(e.get("meta/contents", b"")),
           "meta_package": e.get("meta/package", b"").decode("utf-8", "replace")}
    return m, name, "ok", len(b), rec, texts


def fetch_pkgs(con, items, log=print):
    """items: iterable of (merkle, name). Fetches meta.fars not yet in the store."""
    have = {m for (m,) in con.execute("SELECT merkle FROM pkg")}
    todo = [i for i in dict(items).items() if i[0] not in have]
    with cf.ThreadPoolExecutor(24) as ex:
        for m, name, st, size, rec, texts in ex.map(_pkg_work, todo):
            for t in texts: put_text(con, t)
            con.execute("INSERT OR REPLACE INTO pkg VALUES(?,?,?,?,?)",
                        (m, name, st, size, zlib.compress(json.dumps(rec).encode(), 6) if rec else None))
    con.commit()
    log(f"  packages: {len(todo)} fetched")


def _blob_work(item):
    m, restricted_only = item
    st, h, b = _req(BASE + m, headers={"Range": "bytes=0-8191"})
    if st == 416:
        st, h, b = _req(BASE + m)
        if st == 200: h = {"Content-Range": f"bytes 0-{max(0, len(b) - 1)}/{len(b)}"}
    if st not in (200, 206): return m, f"http {st}", None, None, 0, None, None
    cr = h.get("Content-Range") or h.get("content-range") or ""
    size = int(cr.split("/")[-1]) if "/" in cr else len(b)
    magic = b[:16].hex()
    cand = (not restricted_only) and size <= TEXT_MAX and b"\x00" not in b[:8192]
    if cand:
        try: b[:8192].decode("utf-8")
        except UnicodeDecodeError as e:
            cand = e.start >= len(b[:8192]) - 4
    if not cand: return m, "ok", size, magic, 0, None, None
    full = b if size <= len(b) and st == 200 or (st == 206 and size <= len(b)) else None
    if full is None:
        st2, _, full = _req(BASE + m)
        if st2 != 200: return m, f"http {st2} (full)", size, magic, 0, None, None
    if merkle_root(full) != m: return m, "merkle mismatch", size, magic, 0, None, None
    if not is_text(full): return m, "ok", size, magic, 0, None, ("contains a private key marker" if b"PRIVATE KEY" in full else None)
    return m, "ok", size, magic, 1, full, None


def probe_blobs(con, log=print):
    """Probes every content blob referenced by stored packages that is not probed yet."""
    refs = {}
    for name, rec in con.execute("SELECT name, rec FROM pkg WHERE status='ok'"):
        r = json.loads(zlib.decompress(rec))
        for m in r["contents"].values():
            refs[m] = refs.get(m, True) and r["restricted"]
    have = {m for (m,) in con.execute("SELECT merkle FROM blob")}
    todo = [(m, ro) for m, ro in refs.items() if m not in have]
    with cf.ThreadPoolExecutor(32) as ex:
        for m, st, size, magic, is_t, data, note in ex.map(_blob_work, todo):
            tsha = put_text(con, data) if is_t else None
            con.execute("INSERT OR REPLACE INTO blob VALUES(?,?,?,?,?,?,?)", (m, st, size, magic, is_t, tsha, note))
    con.commit()
    log(f"  content blobs: {len(todo)} probed")
