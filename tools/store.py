"""Shared store for the mirror: SQLite with deduplicated text, package records and blob probe results."""
import sqlite3, zlib, json, hashlib, re
RESTRICTED = {"amlogic-netflix-keys", "widevine-cdm", "playready-cdm", "amlogic-oemcrypto", "provisioning_ta_proxy",
              "trusted-apps", "smart-trusted-apps", "cast_auth", "weave-auth", "astro-optee", "tee-clients", "tee_manager"}
TEXT_MAX = 1_000_000

def connect(path):
    con = sqlite3.connect(path, timeout=120)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS text(sha256 TEXT PRIMARY KEY, data BLOB);
    CREATE TABLE IF NOT EXISTS pkg(merkle TEXT PRIMARY KEY, name TEXT, status TEXT, size INT, rec BLOB);
    CREATE TABLE IF NOT EXISTS blob(merkle TEXT PRIMARY KEY, status TEXT, size INT, magic TEXT, is_text INT, text_sha TEXT, note TEXT);
    """)
    return con

def is_text(b):
    if len(b) > TEXT_MAX or b"\x00" in b[:8192]: return False
    if b"PRIVATE KEY" in b: return False
    try:
        b.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True

def put_text(con, b):
    h = hashlib.sha256(b).hexdigest()
    con.execute("INSERT OR IGNORE INTO text VALUES(?,?)", (h, zlib.compress(b, 6)))
    return h

def get_text(con, h):
    r = con.execute("SELECT data FROM text WHERE sha256=?", (h,)).fetchone()
    return zlib.decompress(r[0]) if r else None

STR_RX = re.compile(rb"[\x20-\x7e]{4,}")
def printable_strings(b):
    seen, out = set(), []
    for m in STR_RX.findall(b):
        s = m.decode("ascii")
        if s not in seen:
            seen.add(s); out.append(s)
    return "\n".join(out) + "\n"
