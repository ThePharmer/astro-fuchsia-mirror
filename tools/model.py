"""Shared model for the mirror: TUF publish events, build parsing, and the release-line plan."""
import json, re, zlib, sqlite3, datetime, collections, urllib.parse

UPD_RX = re.compile(r"^update-smart-display-(user-astro-size-limits|user-astro|user-with-ota)-(\d+)\.(\d{8})\.(\d+)\.(\d+)-(.+)$")
BASE_URL = "https://fuchsia-blobs.googleusercontent.com/"


def parse_update_name(name):
    m = UPD_RX.match(name)
    if not m:
        return None
    var, M, D, R, C, ch = m.groups()
    return dict(name=name, variant=var, milestone=int(M), date=f"{D[:4]}-{D[4:6]}-{D[6:]}", D=D, R=int(R), C=int(C),
                version=f"{M}.{D}.{R}.{C}", channel=ch, canary=ch.startswith("canary"), line=f"{M}.{D}.{R}")


def inferred_time(expires):
    """Signing time inferred as expiry minus 50 years (see README: labelled as an inference)."""
    e = datetime.datetime.fromisoformat(expires.replace("Z", "+00:00"))
    try:
        s = e.replace(year=e.year - 50)
    except ValueError:              # 29 Feb
        s = e.replace(year=e.year - 50, day=28)
    return int(s.timestamp())


def iter_targets(tuf_db, start=1, end=None):
    """Yield (version, raw_bytes, parsed) for targets.json versions in order."""
    con = sqlite3.connect(tuf_db)
    q = "SELECT version, status, data FROM meta WHERE role='targets' AND version>=?" + (" AND version<=?" if end else "") + " ORDER BY version"
    for v, st, d in con.execute(q, (start, end) if end else (start,)):
        if st != 200:
            yield v, None, None
            continue
        raw = zlib.decompress(d)
        yield v, raw, json.loads(raw)


def get_meta(tuf_db, role, version):
    con = sqlite3.connect(tuf_db)
    r = con.execute("SELECT status, data FROM meta WHERE role=? AND version=?", (role, version)).fetchone()
    return zlib.decompress(r[1]) if r and r[0] == 200 else None


def events(tuf_db, start=1, end=None, with_raw=False):
    """Publish events from the cached events table (see build_events.py): per targets version, the
    targets added/changed/removed vs the previous version. with_raw adds the verbatim targets.json bytes."""
    import os
    con = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(tuf_db)), "events.sqlite"))
    q = "SELECT version, time, expires, added, changed, removed FROM events WHERE version>=?" + (" AND version<=?" if end else "") + " ORDER BY version"
    raw_cur = sqlite3.connect(f"file:{os.path.abspath(tuf_db)}?mode=ro", uri=True)
    for v, t, exp, a, c, r in con.execute(q, (start, end) if end else (start,)):
        ev = dict(version=v, missing=False, time=t, expires=exp, added=json.loads(zlib.decompress(a)),
                  changed=json.loads(zlib.decompress(c)), removed=json.loads(zlib.decompress(r)))
        if with_raw:
            row = raw_cur.execute("SELECT data FROM meta WHERE role='targets' AND version=? AND status=200", (v,)).fetchone()
            ev["raw"] = zlib.decompress(row[0]) if row else None
        yield ev


def pins_from_packages_json(text):
    pj = json.loads(text)
    urls = pj.get("content", pj if isinstance(pj, list) else [])
    out = []
    for u in urls:
        p = urllib.parse.urlparse(u)
        out.append((p.path.strip("/").split("/")[0], urllib.parse.parse_qs(p.query).get("hash", [""])[0], u))
    return out


def pins_from_legacy_packages(text):
    out = []
    for line in text.splitlines():
        if "=" in line:
            n, h = line.split("=", 1)
            out.append((n.split("/")[0], h, line))
    return out


def image_packages_from_images_json(text):
    ij = json.loads(text).get("contents", {})
    out = {}
    for kind in ("partitions", "firmware"):
        for x in ij.get(kind, []):
            p = urllib.parse.urlparse(x["url"])
            name = p.path.strip("/").split("/")[0]
            h = urllib.parse.parse_qs(p.query).get("hash", [""])[0]
            out[(name, h)] = True
    return sorted(out)


def plan_lines(builds):
    """builds: {version: [build dicts]} -> (trunk list, lines {line: [versions]}, bases {line: (parent_version, how)}).
    Trunk: canary candidate-1 versions, seeded for F0-F6 with each line's earliest candidate; date order."""
    first = {}
    for v, bs in builds.items():
        b = bs[0]; first[v] = (b["date"], b["milestone"], b["R"], b["C"])
    by_line = collections.defaultdict(list)
    for v, bs in builds.items():
        by_line[bs[0]["line"]].append(v)
    trunk = set()
    for v, bs in builds.items():
        if bs[0]["C"] == 1 and any(b["canary"] for b in bs):
            trunk.add(v)
    for line, vs in by_line.items():
        if builds[vs[0]][0]["milestone"] < 7:
            trunk.add(min(vs, key=lambda v: (builds[v][0]["C"], first[v])))
    trunk = sorted(trunk, key=lambda v: first[v])
    trunk_set = set(trunk)
    lines, bases = {}, {}
    for line, vs in by_line.items():
        rest = sorted((v for v in vs if v not in trunk_set), key=lambda v: (builds[v][0]["C"], first[v]))
        if not rest:
            continue
        lines[line] = rest
        on_trunk = [v for v in vs if v in trunk_set]
        if on_trunk:
            bases[line] = (min(on_trunk, key=lambda v: builds[v][0]["C"]), "line base is on trunk")
        else:
            key = first[rest[0]]
            earlier = [v for v in trunk if first[v] <= key]
            bases[line] = (earlier[-1] if earlier else None,
                           "no trunk base: branched from the latest trunk build on or before " + rest[0] if earlier else "no earlier trunk build: root branch")
    return trunk, lines, bases
