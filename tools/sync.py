"""Daily sync: add new TUF publishes to the GitHub mirror without rewriting anything.

usage: sync.py --url REPO_URL --work DIR [--dry-run] [--push-url URL]

1. Makes a shallow, blobless clone of every branch (a few MB) and reads `state.json` from `mirror-state`.
2. Fetches every TUF targets/snapshot version newer than the last mirrored one, checks each targets.json
   against the sha256 its snapshot records, and fetches the packages and content blobs it needs.
3. Appends commits, using the same rendering as the original build:
   - main: one commit per changed target, one `publish` commit per TUF version, then a bookkeeping commit
     (MISSING, VARIANTS, REPUBLISHED, BASES, LATE_CHANNELS, current timestamp.json). Hand edits made on
     main since the last sync are kept (and copied to condensed) as long as they are plain commits that
     touch none of the files the sync manages; otherwise the sync stops without pushing.
   - condensed: one commit per publish.
   - lines/*: new builds on their release line; channels that arrive after their build was placed go on
     the line if the build is still its tip, otherwise on `lines/late/<version>`; re-publishes on
     `lines/republished/...`; new channel-specific package sets on `lines/variants/...`.
4. Verifies the result, then pushes all branches plus the updated `mirror-state` in one atomic push
   (fast-forward only). Tags are recorded in `mirror-state:tags.txt` for push_tags.sh.
Exit status: 0 = pushed or nothing new, 1 = stopped before pushing (see the printed reason)."""
import sys, os, json, zlib, hashlib, argparse, subprocess, collections, shutil, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import parse_update_name, inferred_time, pins_from_packages_json, pins_from_legacy_packages, image_packages_from_images_json, BASE_URL
from store import connect, get_text
from sync_lib import fetch_pkgs, probe_blobs, tuf_get

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True); ap.add_argument("--work", required=True)
ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--push-url")
ap.add_argument("--init-state", help="first run only: folder with the initial mirror-state branch contents (state.json, tags.txt, README.md, tools/)")
a = ap.parse_args()
AUTHOR = b"Jared <77949461+ThePharmer@users.noreply.github.com>"
AUTHOR_NAME, AUTHOR_EMAIL = "Jared", "77949461+ThePharmer@users.noreply.github.com"
PTR = "fuchsia-mirror/pointer@1"; PKG = "fuchsia-mirror/package@1"
T0 = time.time()
def log(*x): print(f"[{time.time() - T0:5.0f}s]", *x, flush=True)
def stop(reason):
    log("STOPPED:", reason); sys.exit(1)

# ---------------------------------------------------------------- git plumbing (lazy fetching off: every fetch is explicit)
os.makedirs(a.work, exist_ok=True)
R = os.path.join(a.work, "repo.git")
ENV = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
def git(*args, input=None, check=True, text=True):
    r = subprocess.run(["git", "-C", R] + list(args), input=input, capture_output=True, text=text, env=ENV)
    if check and r.returncode:
        stop(f"git {' '.join(args[:3])}: {(r.stderr if text else r.stderr.decode())[-800:]}")
    return r.stdout
if os.path.exists(R): shutil.rmtree(R)
r = subprocess.run(["git", "clone", "-q", "--bare", "--depth", "1", "--no-single-branch", "--no-tags", "--filter=blob:none", a.url, R],
                   capture_output=True, text=True, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
if r.returncode: stop("clone failed: " + r.stderr[-500:])
git("config", "gc.auto", "0")
REMOTE = dict(l.split()[::-1] for l in git("for-each-ref", "--format=%(objectname) %(refname)", "refs/heads").splitlines())
log(f"cloned {len(REMOTE)} branches")

LOCAL = set()
def refresh_local():
    """Objects present locally (cat-file cannot test for a missing object in a partial clone without fetching it)."""
    LOCAL.clear(); LOCAL.update(git("cat-file", "--batch-all-objects", "--batch-check=%(objectname)").split())
refresh_local()
def have(oids):
    return {o for o in oids if o in LOCAL}
def fetch_objects(oids):
    miss = sorted({o for o in oids if o and o not in LOCAL})
    for i in range(0, len(miss), 2000):
        git("-c", "fetch.negotiationAlgorithm=noop", "fetch", "-q", "--no-write-fetch-head", "--filter=blob:none", "origin", "--stdin",
            input="".join(o + "\n" for o in miss[i:i + 2000]))
    if miss: LOCAL.update(miss)
def ensure_commit(sha):
    if sha not in LOCAL:
        git("fetch", "-q", "--no-write-fetch-head", "--depth=1", "--filter=blob:none", "origin", sha)
        refresh_local()
def read_blobs(oids):
    fetch_objects(oids)
    p = subprocess.run(["git", "-C", R, "cat-file", "--batch"], input=b"".join(o.encode() + b"\n" for o in oids), capture_output=True, env=ENV)
    out, i, res = p.stdout, 0, {}
    for o in oids:
        nl = out.index(b"\n", i); head = out[i:nl].split(); i = nl + 1
        if head[1] == b"missing": stop(f"object {o} missing")
        n = int(head[2]); res[o] = out[i:i + n]; i += n + 1
    return res
def ls_tree(rev, *paths):
    rows = git("ls-tree", "-r", "--full-tree", rev, "--", *paths).splitlines()
    return {l.split("\t", 1)[1]: l.split()[2] for l in rows}
def show(rev, path):
    t = ls_tree(rev, path)
    return read_blobs([t[path]])[t[path]] if path in t else None

def tree_from_dir(d):
    """Write a folder into the repo as a tree (used once, to create the mirror-state branch)."""
    rows = []
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.isdir(p): rows.append(f"040000 tree {tree_from_dir(p)}\t{name}")
        else: rows.append(f"100644 blob {git('hash-object', '-w', p).strip()}\t{name}")
    return git("mktree", input="".join(r_ + "\n" for r_ in rows)).strip()
if "refs/heads/mirror-state" not in REMOTE:
    if not a.init_state: stop("no mirror-state branch on the remote (pass --init-state for the first run)")
    t_ = tree_from_dir(a.init_state)
    env_ = dict(ENV, GIT_AUTHOR_NAME=AUTHOR_NAME, GIT_AUTHOR_EMAIL=AUTHOR_EMAIL, GIT_COMMITTER_NAME=AUTHOR_NAME, GIT_COMMITTER_EMAIL=AUTHOR_EMAIL)
    c_ = subprocess.run(["git", "-C", R, "commit-tree", t_], input="Sync state and tools\n\nState as of the full build (TUF targets v13221).\n",
                        capture_output=True, text=True, env=env_, check=True).stdout.strip()
    git("update-ref", "refs/heads/mirror-state", c_)
    refresh_local()
    REMOTE_STATE_BASE = None; STATE_REF = c_
else:
    REMOTE_STATE_BASE = REMOTE["refs/heads/mirror-state"]; STATE_REF = "refs/heads/mirror-state"
state = json.loads(show(STATE_REF, "state.json"))
if REMOTE.get("refs/heads/condensed") != state["condensed"]:
    stop("condensed on GitHub is not where the last sync left it; not touching anything")
# Hand edits on main are accepted when they sit on top of the last sync, are plain (non-merge) commits and
# touch nothing the sync manages. They are carried over to condensed unchanged.
MANAGED = ("tuf/", "builds/", "named/", "MISSING.md", "VARIANTS.md", "REPUBLISHED.md", "BASES.md", "LATE_CHANNELS.md")
MAIN_BASE = REMOTE.get("refs/heads/main"); HAND = []
if MAIN_BASE != state["main"]:
    for depth in (50, 400):
        git("fetch", "-q", "--no-write-fetch-head", f"--depth={depth}", "--filter=blob:none", "origin", "refs/heads/main")
        refresh_local()
        if state["main"] in LOCAL: break
    else:
        stop("main on GitHub does not contain the last synced commit within 400 commits; not touching anything")
    rows = [l.split() for l in git("rev-list", "--parents", "--reverse", f"{state['main']}..{MAIN_BASE}").splitlines()]
    prev_ = state["main"]
    for row in rows:
        if len(row) != 2 or row[1] != prev_:
            stop(f"main on GitHub has a merge or rewritten history after the last sync (at {row[0][:10]}); not touching anything")
        touched_ = [x for x in git("diff-tree", "-r", "--no-commit-id", "--name-only", row[0]).splitlines() if x.startswith(MANAGED)]
        if touched_:
            stop(f"hand edit {row[0][:10]} on main changes files the sync manages ({', '.join(touched_[:3])}); not touching anything")
        HAND.append(row[0]); prev_ = row[0]
    log(f"main has {len(HAND)} hand edit(s) since the last sync; building on top of them")
LAST = state["last_tuf"]

# ---------------------------------------------------------------- 1. new TUF versions
st_, ts_raw = tuf_get("timestamp.json")
if st_ != 200: stop(f"timestamp.json: http {st_}")
snap_v = json.loads(ts_raw)["signed"]["meta"]["snapshot.json"]["version"]
st_, s = tuf_get(f"{snap_v}.snapshot.json")
if st_ != 200: stop(f"{snap_v}.snapshot.json: http {st_}")
NEWEST = json.loads(s)["signed"]["meta"]["targets.json"]["version"]
log(f"mirror has TUF v{LAST}, source is at v{NEWEST}")
if NEWEST <= LAST:
    log("RESULT: up to date, nothing pushed"); sys.exit(0)

import concurrent.futures as cf
with cf.ThreadPoolExecutor(16) as ex:
    got = dict(zip([(r_, v) for v in range(LAST + 1, NEWEST + 1) for r_ in ("targets", "snapshot")],
                   ex.map(lambda x: tuf_get(f"{x[1]}.{x[0]}.json"), [(r_, v) for v in range(LAST + 1, NEWEST + 1) for r_ in ("targets", "snapshot")])))
for v in range(LAST + 1, NEWEST + 1):
    tst, traw = got[("targets", v)]; sst, sraw = got[("snapshot", v)]
    if tst == 200 and sst == 200:
        meta = json.loads(sraw)["signed"]["meta"].get("targets.json", {})
        h = meta.get("hashes", {}).get("sha256")
        if meta.get("version") == v and h and hashlib.sha256(traw).hexdigest() != h:
            stop(f"targets.json v{v} does not match the sha256 in snapshot v{v}")
    if tst not in (200, 404) or sst not in (200, 404):
        stop(f"TUF v{v}: unexpected http {tst}/{sst}; will retry next run")
prev = json.loads(show("refs/heads/main", "tuf/targets.json"))["signed"]["targets"]
evs = []
for v in range(LAST + 1, NEWEST + 1):
    tst, traw = got[("targets", v)]; sst, sraw = got[("snapshot", v)]
    if tst != 200:
        evs.append(dict(version=v, missing=True)); continue
    sg = json.loads(traw)["signed"]; t = sg.get("targets", {})
    evs.append(dict(version=v, missing=False, time=inferred_time(sg["expires"]), expires=sg["expires"], raw=traw,
                    snap=sraw if sst == 200 else None,
                    added={k: t[k] for k in t.keys() - prev.keys()}, changed={k: t[k] for k in t.keys() & prev.keys() if t[k] != prev[k]},
                    removed=sorted(prev.keys() - t.keys())))
    prev = t
log(f"{len(evs)} new TUF versions ({sum(e['missing'] for e in evs)} not served)")

# ---------------------------------------------------------------- 2. per-run store: packages for every changed target
con = connect(os.path.join(a.work, "store.sqlite"))
need = {}
for ev in evs:
    if ev["missing"]: continue
    for k, e in list(ev["added"].items()) + list(ev["changed"].items()):
        need[e["custom"]["merkle"]] = k.rsplit("/", 1)[0]
for k, c in state["channels"].items():          # previous update package of anything re-published, for its file diff
    for ev in evs:
        if not ev["missing"] and k in ev["changed"] and ev["changed"][k]["custom"]["merkle"] != c["merkle"]:
            need[c["merkle"]] = k.rsplit("/", 1)[0]
log(f"fetching {len(need)} package versions for changed targets")
fetch_pkgs(con, need.items(), log=log); probe_blobs(con, log=log)

# ---------------------------------------------------------------- 3. rendering (same as gen_git.py)
PLAN = [True]; NEED = {}
_mark = [0]; _blobs = {}; OUT = []
def new_mark():
    _mark[0] += 1
    return _mark[0]
def blob(data):
    if PLAN[0]: return 0
    k = hashlib.sha1(data).digest(); m = _blobs.get(k)
    if m is None:
        m = new_mark(); _blobs[k] = m
        OUT.append(b"blob\nmark :%d\ndata %d\n" % (m, len(data))); OUT.append(data); OUT.append(b"\n")
    return m
def qpath(p):
    return json.dumps(p) if p.startswith('"') or "\n" in p else p
def ref_of(p):
    return b":%d" % p if isinstance(p, int) else p.encode()
def commit(branch, msg, t, ops, parent=None):
    m = new_mark()
    if PLAN[0]: return m
    body = (msg + "\n").encode()
    OUT.append(b"commit refs/heads/%s\nmark :%d\n" % (branch.encode(), m))
    OUT.append(b"author %s %d +0000\ncommitter %s %d +0000\n" % (AUTHOR, t, AUTHOR, t))
    OUT.append(b"data %d\n" % len(body)); OUT.append(body); OUT.append(b"\n")
    if parent: OUT.append(b"from %s\n" % ref_of(parent))
    for op in ops:
        if op[0] == "D": OUT.append(b"D %s\n" % qpath(op[1]).encode())
        else: OUT.append(b"M 100644 :%d %s\n" % (op[2], qpath(op[1]).encode()))
    OUT.append(b"\n")
    return m
NEW_TAGS = []
def tag(name, mark):
    if PLAN[0]: return
    OUT.append(b"reset refs/tags/%s\nfrom %s\n\n" % (name.encode(), ref_of(mark))); NEW_TAGS.append(name)
def jdump(o):
    return (json.dumps(o, indent=2, sort_keys=False) + "\n").encode()

def blob_info(m):
    return con.execute("SELECT status, size, magic, is_text, text_sha, note FROM blob WHERE merkle=?", (m,)).fetchone()
def pkg_rec(merkle):
    r = con.execute("SELECT name, status, size, rec FROM pkg WHERE merkle=?", (merkle,)).fetchone()
    if not r: return None
    return dict(name=r[0], status=r[1], size=r[2], rec=json.loads(zlib.decompress(r[3])) if r[3] else None)

def render(merkle, name):
    files = []; p = pkg_rec(merkle); url = BASE_URL + merkle
    if p is None and not PLAN[0]: stop(f"package {merkle} ({name}) was not fetched")
    if not p or p["status"] != "ok":
        status = p["status"] if p else "not fetched"
        files.append(("PACKAGE.json", blob(jdump({"schema": PKG, "name": name, "status": status,
                      "meta_far": {"merkle": merkle, "url": url}, "note": "meta.far could not be retrieved; listed in MISSING.md"}))))
        return files
    rec = p["rec"]; restricted = rec["restricted"]
    derived, n_text, n_ptr = [], 0, 0
    for e in rec["entries"]:
        path = e["path"]
        if "text" in e:
            files.append((path, blob(get_text(con, e["text"])))); n_text += 1
        else:
            files.append((path + ".ptr.json", blob(jdump({"schema": PTR, "kind": "far-entry", "far_merkle": merkle, "far_url": url, "path": path,
                          "size": e["size"], "sha256": e["sha256"], "restricted": restricted, "summary": None})))); n_ptr += 1
            if "strings" in e:
                files.append((path + ".strings.txt", blob(get_text(con, e["strings"])))); derived.append(path + ".strings.txt")
    for path, m in sorted(rec["contents"].items()):
        bi = blob_info(m)
        if bi and bi[3] and not restricted:
            files.append(("files/" + path, blob(get_text(con, bi[4])))); n_text += 1
        else:
            ptr = {"schema": PTR, "kind": "blob", "merkle": m, "url": BASE_URL + m}
            if bi:
                ptr.update(size=bi[1], magic=bi[2], status=bi[0])
                if bi[5]: ptr["note"] = bi[5]
            else:
                ptr.update(status="not probed")
            ptr.update(restricted=restricted, summary=None)
            files.append(("files/" + path + ".ptr.json", blob(jdump(ptr)))); n_ptr += 1
    meta = {"schema": PKG, "name": name, "status": "ok", "meta_far": {"merkle": merkle, "size": p["size"], "url": url},
            "meta_package": rec["meta_package"], "restricted": restricted, "content_files": len(rec["contents"]),
            "meta_entries": len(rec["entries"]), "inline_text_files": n_text, "pointer_files": n_ptr, "derived_files": derived}
    files.insert(0, ("PACKAGE.json", blob(jdump(meta))))
    return files

def folder_ops(prefix, merkle, name):
    if PLAN[0]:
        NEED[merkle] = name; return []
    return [("D", prefix)] + [("M", prefix + "/" + rel, mk) for rel, mk in render(merkle, name)]

def text_of(rec, path):
    m = rec["contents"].get(path)
    if not m: return None
    bi = blob_info(m)
    return get_text(con, bi[4]).decode() if bi and bi[3] else None

def chan(b): return f"{b['variant']}-{b['channel']}"
def pins_of(b):
    if not b["rec"]: return None
    pj = text_of(b["rec"], "packages.json")
    if pj is not None: pins = pins_from_packages_json(pj)
    else:
        lp = text_of(b["rec"], "packages"); pins = pins_from_legacy_packages(lp) if lp else []
    imgs = []
    ij = text_of(b["rec"], "images.json")
    if ij: imgs = image_packages_from_images_json(ij)
    return tuple(sorted((n, h) for n, h, _ in pins)), tuple(imgs)
def digest(key):
    return None if key is None else hashlib.sha256(json.dumps(key).encode()).hexdigest()
def rec_of(m):
    p = pkg_rec(m)
    return p["rec"] if p and p["status"] == "ok" else None

# ---------------------------------------------------------------- 4. state of an existing commit, read from its tree
TREE_STATE = {}
def state_at(ref):
    """(packages, images, update packages) at a commit: an in-run mark (kept in memory) or a GitHub commit."""
    if ref in TREE_STATE: return cp(TREE_STATE[ref])
    ensure_commit(ref)
    t = ls_tree(ref, "packages", "update")
    want = {p: o for p, o in t.items() if p.endswith("/PACKAGE.json") and (p.count("/") == 2 or p.split("/")[2] in ("images", "update-package"))}
    data = read_blobs(sorted(set(want.values())))
    pk, im, up = {}, {}, {}
    for p, o in want.items():
        mk = json.loads(data[o])["meta_far"]["merkle"]; parts = p.split("/")
        if parts[0] == "packages" and len(parts) == 3: pk[parts[1]] = mk
        elif parts[0] == "update" and parts[2] == "images" and len(parts) == 5: im[(parts[1], parts[3])] = mk
        elif parts[0] == "update" and parts[2] == "update-package" and len(parts) == 4: up[parts[1]] = mk
    TREE_STATE[ref] = (pk, im, up)
    return cp(TREE_STATE[ref])
def cp(st): return tuple(dict(x) for x in st)
BUILD_JSON = {}
def build_json_at(ref):
    if ref in BUILD_JSON: return json.loads(json.dumps(BUILD_JSON[ref]))
    ensure_commit(ref); return json.loads(show(ref, "BUILD.json"))

pkg_path = lambda n: (f"packages/{n}", n)
img_path = lambda key: (f"update/{key[0]}/images/{key[1]}", key[1])
def diff_commits(branch, prev, t, cur, want, path_of, label, context):
    for key in sorted(set(cur) | set(want)):
        if cur.get(key) == want.get(key): continue
        path, name = path_of(key)
        if key in want:
            ops = folder_ops(path, want[key], name)
            msg = f"{name}: {cur.get(key, '(new)')[:12]} -> {want[key][:12]}\n\n{label} {name} {want[key]}\n{context}"
        else:
            ops = [("D", path)]
            msg = f"{name}: removed\n\n{label} {name} (was {cur[key]})\n{context}"
        prev = commit(branch, msg, t, ops, parent=prev)
        if key in want: cur[key] = want[key]
        else: cur.pop(key, None)
    return prev
def images_for(b, im):
    k = pins_of(b)
    if k is None: return {key: m for key, m in im.items() if key[0] == chan(b)}
    return {(chan(b), n): h for n, h in k[1]}
def channel_entry(b):
    return {"channel": chan(b), "target": b["target"], "update_merkle": b["merkle"], "tuf_version_first_seen": b["tuf_version"],
            "image_packages": {n: h for n, h in (pins_of(b) or ((), ()))[1]}}
def build_info(v, group, t, npins, extra=None):
    info = {"version": v, "milestone": group[0]["milestone"], "branch_date": group[0]["date"], "line": group[0]["line"],
            "first_published": t, "first_published_note": "inferred: targets.json expiry minus 50 years",
            "pinned_packages": npins, "channels": [channel_entry(b) for b in group]}
    if extra: info.update(extra)
    return info
def set_channels(branch, prev, t, st, group, context):
    pk, im, up = st
    want_im = {}
    for b in group: want_im.update(images_for(b, im))
    prev = diff_commits(branch, prev, t, im, want_im, img_path, "image package", context)
    ops = []; want_up = {chan(b): b for b in group}
    for ch in sorted(set(up) - set(want_up)):
        ops.append(("D", f"update/{ch}")); up.pop(ch)
    for ch, b in sorted(want_up.items()):
        if up.get(ch) != b["merkle"]:
            ops += folder_ops(f"update/{ch}/update-package", b["merkle"], b["name"]); up[ch] = b["merkle"]
    return prev, ops

# ---------------------------------------------------------------- 5. the run (executed twice: plan, then emit)
def run():
    S = json.loads(json.dumps(state))
    docs = collections.defaultdict(list)
    tips = {}                                      # branch -> ref (in-run mark or sha)
    def tip(br):
        return tips.get(br) or REMOTE.get("refs/heads/" + br)
    trunk_first = {v: tuple(f) for v, f, _ in S["trunk"]}
    for v, info in S["versions"].items():
        info["first"] = tuple(info["first"])

    # collect update-target events
    new_t, later, meta_only = {}, collections.defaultdict(list), collections.Counter()
    cur_m = {k: c["merkle"] for k, c in S["channels"].items()}
    for ev in evs:
        if ev["missing"]: continue
        for k, e in sorted(list(ev["added"].items()) + list(ev["changed"].items())):
            if not k.startswith("update-smart-display"): continue
            m = e["custom"]["merkle"]
            if k in cur_m:
                if m != cur_m[k]: later[k].append((ev["time"], ev["version"], m)); cur_m[k] = m
                else: meta_only[ev["version"]] += 1
            else:
                b = parse_update_name(k.rsplit("/", 1)[0])
                if not b: continue
                b.update(target=k, merkle=m, time=ev["time"], tuf_version=ev["version"], rec=rec_of(m))
                new_t[k] = b; cur_m[k] = m
    by_v = collections.defaultdict(list)
    for b in new_t.values(): by_v[b["version"]].append(b)
    for v in by_v: by_v[v].sort(key=lambda b: (not b["canary"], b["variant"], b["channel"]))
    first_of = lambda bs: (bs[0]["date"], bs[0]["milestone"], bs[0]["R"], bs[0]["C"])

    # 5a. new build versions, in order of first publish
    def emit_version(branch, v, st, parent):
        bs = by_v[v]; groups = collections.OrderedDict()
        for b in bs:
            k = pins_of(b); groups.setdefault(k[0] if k else None, []).append(b)
        primary_key = next(iter(groups)); prim = groups[primary_key]
        t = min(b["time"] for b in bs)
        st = cp(st); pk = st[0]
        if primary_key is None:
            docs["missing"].append(f"| build {v} | update package or packages.json unavailable for {', '.join(chan(b) for b in prim)}; packages carried over unchanged |")
            want_pk = dict(pk)
        else:
            want_pk = dict(primary_key)
        prev = diff_commits(branch, parent, t, pk, want_pk, pkg_path, "package", f"build {v}")
        prev, ops = set_channels(branch, prev, t, st, prim, f"build {v}")
        info = build_info(v, prim, t, len(want_pk)); ops.append(("M", "BUILD.json", blob(jdump(info))))
        final = commit(branch, f"build {v} ({', '.join(chan(b) for b in prim)})\n\npinned packages: {len(want_pk)}\nfirst published (inferred): TUF v{min(b['tuf_version'] for b in prim)}", t, ops, parent=prev)
        TREE_STATE[final] = cp(st); BUILD_JSON[final] = info
        tag(f"v/{v}", final)
        gl = [{"branch": branch, "commit": final, "channels": [chan(b) for b in prim], "pins": digest(primary_key)}]
        for b in prim:
            tag(f"ch/{chan(b)}/{v}", final)
            S["channels"][b["target"]] = {"version": v, "channel": chan(b), "merkle": b["merkle"], "commit": final, "republished": 0}
        for k, (key, gb) in enumerate(list(groups.items())[1:], 1):
            vb = f"lines/variants/{v}-{k}"
            vst = cp(st); vwant = dict(key) if key else dict(vst[0])
            diff = sorted(n for n in set(vwant) | set(want_pk) if vwant.get(n) != want_pk.get(n))
            vprev = diff_commits(vb, final, t, vst[0], vwant, pkg_path, "package", f"build {v} variant {k}")
            vprev, vops = set_channels(vb, vprev, t, vst, gb, f"build {v} variant {k}")
            vinfo = build_info(v, gb, t, len(vwant), {"variant_of": v}); vops.append(("M", "BUILD.json", blob(jdump(vinfo))))
            vm = commit(vb, f"build {v} variant {k} ({', '.join(chan(b) for b in gb)})\n\npackages differing from the shared set: {', '.join(diff)}", t, vops, parent=vprev)
            TREE_STATE[vm] = cp(vst); BUILD_JSON[vm] = vinfo; tips[vb] = vm
            for b in gb:
                tag(f"ch/{chan(b)}/{v}", vm)
                S["channels"][b["target"]] = {"version": v, "channel": chan(b), "merkle": b["merkle"], "commit": vm, "republished": 0}
            docs["variants"].append(f"| {v} | {vb} | {', '.join(chan(b) for b in gb)} | {', '.join(diff)} |")
            gl.append({"branch": vb, "commit": vm, "channels": [chan(b) for b in gb], "pins": digest(key)})
        S["versions"][v] = {"branch": branch, "first": first_of(bs), "time": t, "groups": gl}
        return final

    new_versions = sorted((v for v in by_v if v not in S["versions"]), key=lambda v: (min(b["time"] for b in by_v[v]), first_of(by_v[v])))
    for v in new_versions:
        bs = by_v[v]
        if bs[0]["C"] == 1 and any(b["canary"] for b in bs):
            br = "lines/main"
        else:
            line = bs[0]["line"]; br = f"lines/releases/{line}"
            if not tip(br):
                on_trunk = [(trunk_first[w][3], w) for w in trunk_first if w.rsplit(".", 1)[0] == line]
                if on_trunk:
                    pv = min(on_trunk)[1]; how = "line base is on trunk"
                else:
                    earlier = [w for w in trunk_first if trunk_first[w] <= first_of(bs)]
                    pv = max(earlier, key=lambda w: trunk_first[w]) if earlier else None
                    how = ("no trunk base: branched from the latest trunk build on or before " + v) if earlier else "no earlier trunk build: root branch"
                if pv is None: stop(f"no base for new release line {line}")
                tips[br] = S["versions"][pv]["groups"][0]["commit"]
                S["bases"][line] = [pv, how]
                docs["bases"].append(f"| {line} | {v} | {pv} | {how} |")
        parent = tip(br)
        final = emit_version(br, v, state_at(parent), parent)
        tips[br] = final
        if br == "lines/main":
            trunk_first[v] = first_of(bs); S["trunk"].append([v, list(first_of(bs)), final])

    # 5b. channels that arrived after their build was placed
    for v in sorted(v for v in by_v if v not in new_versions):
        info = S["versions"][v]
        for b in sorted(by_v[v], key=lambda b: (b["time"], b["tuf_version"], chan(b))):
            ch = chan(b); key = pins_of(b); d = digest(key[0] if key else None)
            t = b["time"]; ctx = f"build {v}: channel {ch} added (TUF v{b['tuf_version']})"
            gi = next((i for i, g in enumerate(info["groups"]) if g["pins"] == d), None)
            if gi is None:                                  # a new channel-specific package set
                k = len(info["groups"]); vb = f"lines/variants/{v}-{k}"; base = info["groups"][0]["commit"]
                vst = state_at(base); want_pk = dict(vst[0])
                vwant = dict(key[0]) if key else dict(vst[0])
                diff = sorted(n for n in set(vwant) | set(want_pk) if vwant.get(n) != want_pk.get(n))
                vprev = diff_commits(vb, base, t, vst[0], vwant, pkg_path, "package", f"build {v} variant {k}")
                vprev, vops = set_channels(vb, vprev, t, vst, [b], f"build {v} variant {k}")
                vinfo = build_info(v, [b], info["time"], len(vwant), {"variant_of": v}); vops.append(("M", "BUILD.json", blob(jdump(vinfo))))
                vm = commit(vb, f"build {v} variant {k} ({ch})\n\npackages differing from the shared set: {', '.join(diff)}\nchannel arrived after the build was placed (TUF v{b['tuf_version']})", t, vops, parent=vprev)
                TREE_STATE[vm] = cp(vst); BUILD_JSON[vm] = vinfo; tips[vb] = vm
                info["groups"].append({"branch": vb, "commit": vm, "channels": [ch], "pins": d, "last": vm})
                docs["variants"].append(f"| {v} | {vb} | {ch} | {', '.join(diff)} |")
                docs["late"].append(f"| {v} | {ch} | v{b['tuf_version']} | {vb} (new package set) |")
                where = vm
            else:
                g = info["groups"][gi]
                if tip(g["branch"]) == g.get("last", g["commit"]):
                    br = g["branch"]
                else:
                    br = f"lines/late/{v}" + (f"-{gi}" if gi else "")
                    g["late_branch"] = br
                parent = tip(br) or g["commit"]
                st = state_at(parent); pk, im, up = st
                want_im = {k2: h for k2, h in im.items() if k2[0] != ch}; want_im.update(images_for(b, im))
                prev = diff_commits(br, parent, t, im, want_im, img_path, "image package", ctx)
                ops = folder_ops(f"update/{ch}/update-package", b["merkle"], b["name"]); up[ch] = b["merkle"]
                bj = build_json_at(parent) if not PLAN[0] else {"channels": []}
                bj["channels"] = [c for c in bj["channels"] if c["channel"] != ch] + [channel_entry(b)]
                ops.append(("M", "BUILD.json", blob(jdump(bj))))
                where = commit(br, f"build {v}: channel {ch} added\n\nfirst published (inferred): TUF v{b['tuf_version']}\nupdate package {b['merkle']}", t, ops, parent=prev)
                TREE_STATE[where] = cp(st); BUILD_JSON[where] = bj; tips[br] = where
                if br == g["branch"]: g["last"] = where
                g["channels"].append(ch)
                docs["late"].append(f"| {v} | {ch} | v{b['tuf_version']} | {br} |")
            tag(f"ch/{ch}/{v}", where)
            S["channels"][b["target"]] = {"version": v, "channel": ch, "merkle": b["merkle"], "commit": where, "republished": 0}

    # 5c. re-published update packages
    for k in sorted(later):
        c = S["channels"][k]; v, ch = c["version"], c["channel"]
        base = parse_update_name(k.rsplit("/", 1)[0])
        prev_m = c["merkle"]; prev_rec = rec_of(prev_m)
        br = f"lines/republished/{v}-{ch}"
        for t, tv, m in later[k]:
            n = c["republished"] + 1
            parent = c["commit"]; st = state_at(parent)
            rec = rec_of(m)
            if rec:
                old = prev_rec["contents"] if prev_rec else {}
                changed_files = sorted(f for f in set(rec["contents"]) | set(old) if rec["contents"].get(f) != old.get(f))
            else:
                changed_files = ["(new update package unavailable)"]
            nb = dict(base, target=k, rec=rec, merkle=m, time=t, tuf_version=tv)
            kk = pins_of(nb); ctx = f"re-published build {base['name']} (TUF v{tv})"; prev = parent
            if kk: prev = diff_commits(br, prev, t, st[0], dict(kk[0]), pkg_path, "package", ctx)
            want_im = {key: h for key, h in st[1].items() if key[0] != ch}; want_im.update(images_for(nb, st[1]))
            prev = diff_commits(br, prev, t, st[1], want_im, img_path, "image package", ctx)
            ops = folder_ops(f"update/{ch}/update-package", m, base["name"]); st[2][ch] = m
            replaced = (prev_m if prev_rec else None) if n == 1 else "(previous re-publish)"
            prev = commit(br, f"re-published {base['name']}\n\nTUF v{tv} replaced update package {replaced}\nnew update package {m}\nfiles changed: {', '.join(changed_files)}", t, ops, parent=prev)
            TREE_STATE[prev] = cp(st); tips[br] = prev
            tag(f"republished/{ch}/{v}/{n}", prev)
            docs["republished"].append(f"| {base['name']} | v{tv} | {', '.join(changed_files)} | {br} |")
            c.update(commit=prev, merkle=m, republished=n); prev_m, prev_rec = m, rec
    for tv, n in sorted(meta_only.items()):
        docs["meta_only"].append(f"| v{tv} | {n} |")

    # 5d. main: publish history, exactly as gen_git.py pass 2
    main_parent = MAIN_BASE; entry_state = json.loads(show("refs/heads/main", "tuf/targets.json"))["signed"]["targets"] if not PLAN[0] else {}
    for ev in evs:
        v = ev["version"]
        if ev["missing"]:
            docs["missing"].append(f"| targets.json v{v} | not served by the repo host |"); continue
        t = ev["time"]
        for k, e in sorted(list(ev["added"].items()) + list(ev["changed"].items())):
            old = entry_state.get(k)
            if old is None: what = "added"
            else:
                fields = [f for f in sorted(set(old) | set(e)) if old.get(f) != e.get(f)]; sub = []
                for f in fields:
                    if isinstance(old.get(f), dict) and isinstance(e.get(f), dict):
                        sub += [f"{f}.{x}" for x in sorted(set(old[f]) | set(e[f])) if old[f].get(x) != e[f].get(x)]
                    else: sub.append(f)
                what = "changed " + ", ".join(sub)
            entry_state[k] = e
            name = k.rsplit("/", 1)[0]; b = parse_update_name(name)
            path = f"builds/F{b['milestone']:02d}/{b['version']}/{b['variant']}-{b['channel']}" if b else f"named/{name}"
            m = e["custom"]["merkle"]
            msg = f"{name} -> {m[:12]} ({what})\n\ntarget {k}\nmerkle {m}\nlength {e.get('length')}\nsha256 {e.get('hashes', {}).get('sha256')}\nTUF targets v{v}"
            main_parent = commit("main", msg, t, folder_ops(path, m, name), parent=main_parent)
        for k in ev["removed"]:
            name = k.rsplit("/", 1)[0]; b = parse_update_name(name)
            path = f"builds/F{b['milestone']:02d}/{b['version']}/{b['variant']}-{b['channel']}" if b else f"named/{name}"
            main_parent = commit("main", f"{name}: removed from targets\n\nTUF targets v{v}", t, [("D", path)], parent=main_parent)
        ops = [("M", "tuf/targets.json", blob(ev["raw"]))] + ([("M", "tuf/snapshot.json", blob(ev["snap"]))] if ev["snap"] else [])
        msg = (f"publish: TUF targets v{v}\n\n{len(ev['added'])} added, {len(ev['changed'])} changed, {len(ev['removed'])} removed\n"
               f"signed (inferred from expiry minus 50 years): {t}\nexpires: {ev['expires']}")
        main_parent = commit("main", msg, t, ops, parent=main_parent)
        tag(f"tuf/v{v}", main_parent)
    return S, docs, tips, main_parent

log("planning")
S, docs, tips, _ = run()
log(f"fetching {len(NEED)} package versions for the release branches")
fetch_pkgs(con, NEED.items(), log=log); probe_blobs(con, log=log)
PLAN[0] = False; _mark[0] = 0
for d_ in (TREE_STATE, BUILD_JSON):                 # forget the planning pass's placeholder marks
    for k_ in [k_ for k_ in d_ if isinstance(k_, int)]: del d_[k_]
log("emitting commits")
S, docs, tips, main_tip = run()

# ---------------------------------------------------------------- 6. bookkeeping commit on main
def rows_into(md, rows, before=None):
    if not rows: return md
    md = md if md.endswith("\n") else md + "\n"
    if before and before in md:
        i = md.index(before); head = md[:i].rstrip("\n") + "\n"
        return head + "\n".join(rows) + "\n\n" + md[i:]
    return md + "\n".join(rows) + "\n"
cur_docs = {p: show("refs/heads/main", p) for p in ("MISSING.md", "VARIANTS.md", "REPUBLISHED.md", "BASES.md", "LATE_CHANNELS.md", "README.md")}
for (m, name, st_) in con.execute("SELECT merkle, name, status FROM pkg WHERE status!='ok'"):
    if m not in S["failed_pkgs"]: docs["missing"].append(f"| package meta.far {m} ({name}) | {st_} |"); S["failed_pkgs"].append(m)
for (m, st_) in con.execute("SELECT merkle, status FROM blob WHERE status!='ok'"):
    if m not in S["failed_blobs"]: docs["missing"].append(f"| content blob {m} | {st_} |"); S["failed_blobs"].append(m)
LATE_HEAD = ("# Channels added after their build\n\nThe daily sync places each build when it first appears. When another channel ships the same build later, "
             "it is added on the build's branch if the build is still that branch's newest, and otherwise on a `lines/late/<version>` side branch "
             "that starts from the build's commit. A channel whose package set differs gets a `lines/variants/...` branch instead. "
             "The channel tag `ch/<channel>/<version>` points at the commit that added it.\n\n"
             "| Build | Channel | First published | Commit is on |\n|---|---|---|---|\n")
SYNC_README = ("\n## Daily sync\n\nA scheduled job adds new TUF publishes every day: commits are only appended, never rewritten. "
               "Each run adds the new `publish` history to `main` and `condensed`, new builds to their release line, re-publishes to "
               "`lines/republished/...`, and channels that arrive after their build was placed as described in "
               "[LATE_CHANNELS.md](LATE_CHANNELS.md). Builds placed by the sync use the channels known when they first appeared, so a "
               "build whose canary channel arrives later stays on its release line. The `mirror-state` branch holds the sync's "
               "state, its code, and `tags.txt`, the full tag list (run `push_tags.sh` from that branch to push tags).\n")
newdocs = {
    "MISSING.md": rows_into(cur_docs["MISSING.md"].decode(), docs["missing"]),
    "VARIANTS.md": rows_into(cur_docs["VARIANTS.md"].decode(), docs["variants"]),
    "BASES.md": rows_into(cur_docs["BASES.md"].decode(), docs["bases"]),
    "LATE_CHANNELS.md": rows_into((cur_docs["LATE_CHANNELS.md"] or LATE_HEAD.encode()).decode(), docs["late"]),
}
rp = rows_into(cur_docs["REPUBLISHED.md"].decode(), docs["republished"], before="\n## Target entries edited")
newdocs["REPUBLISHED.md"] = rows_into(rp, docs["meta_only"])
readme = cur_docs["README.md"].decode()
if "## Daily sync" not in readme: newdocs["README.md"] = readme.rstrip("\n") + "\n" + SYNC_README
ops = [("M", p, blob(d.encode())) for p, d in sorted(newdocs.items()) if (cur_docs.get(p) or b"").decode() != d]
ops.append(("M", "tuf/timestamp.json", blob(ts_raw)))
rv = S.get("root_version", 4); roots = []
while True:
    st_, rb = tuf_get(f"{rv + 1}.root.json")
    if st_ != 200: break
    rv += 1; roots.append(rv); ops.append(("M", "tuf/root.json", blob(rb)))
S["root_version"] = rv
last_t = max(e["time"] for e in evs if not e["missing"]) if any(not e["missing"] for e in evs) else int(time.time())
bk = commit("main", f"Record missing items and current timestamp.json\n\nsync through TUF targets v{NEWEST}" + (f"\nnew TUF root: v{roots[-1]}" if roots else ""),
            last_t, ops, parent=main_tip)

# ---------------------------------------------------------------- 7. import, then condensed and mirror-state
OUT.append(b"done\n")
marks_file = os.path.join(a.work, "marks")
p = subprocess.run(["git", "-C", R, "fast-import", "--quiet", "--done", f"--export-marks={marks_file}"], input=b"".join(OUT), capture_output=True, env=ENV)
if p.returncode: stop("fast-import: " + p.stderr.decode()[-1500:])
MARKS = {int(l.split()[0][1:]): l.split()[1] for l in open(marks_file)}
res = lambda r_: MARKS[r_] if isinstance(r_, int) else r_
log(f"imported {len(MARKS)} objects")
refresh_local()

main_new = git("rev-parse", "refs/heads/main").strip()
def condense():
    raw = git("log", "--first-parent", "--reverse", "--format=%H%x00%T%x00%an%x00%ae%x00%ad%x00%cn%x00%ce%x00%cd%x00%B%x01", "--date=raw", f"{state['main']}..{main_new}")
    parent = state["condensed"]; pending = []; recs = [x.lstrip("\n") for x in raw.split("\x01") if x.strip()]
    for i, rec in enumerate(recs):
        h, t, an, ae, ad, cn, ce, cd, body = rec.split("\x00", 8); body = body.rstrip("\n"); subject = body.split("\n", 1)[0]
        env = dict(ENV, GIT_AUTHOR_NAME=an, GIT_AUTHOR_EMAIL=ae, GIT_AUTHOR_DATE=ad, GIT_COMMITTER_NAME=cn, GIT_COMMITTER_EMAIL=ce, GIT_COMMITTER_DATE=cd)
        if h in HAND:                                   # a hand edit on main: carried over as it is
            if pending: stop("hand edit in the middle of a publish")
            msg = body + "\n"
        elif subject.startswith("publish:"):
            rest = (body.split("\n", 1)[1] if "\n" in body else "").strip("\n")
            msg = subject + "\n\n" + (f"{len(pending)} target change(s) in this publish (one commit each on main):\n" + "\n".join("- " + x for x in pending)
                                       if pending else "No target changes in this publish (metadata re-sign only).") + "\n\n" + (rest + "\n\n" if rest else "")
            msg = msg.rstrip("\n") + "\n"; pending = []
        elif i == len(recs) - 1:
            if pending: stop("target commits before the bookkeeping commit without a publish")
            msg = body + "\n"
        else:
            pending.append(subject); continue
        parent = subprocess.run(["git", "-C", R, "commit-tree", t, "-p", parent], input=msg, capture_output=True, text=True, env=env, check=True).stdout.strip()
    return parent
cond_new = condense()
git("update-ref", "refs/heads/condensed", cond_new)

S["main"] = main_new; S["condensed"] = cond_new; S["last_tuf"] = NEWEST
for v, info in S["versions"].items():
    info["first"] = list(info["first"])
    for g in info["groups"]:
        for f in ("commit", "last"):
            if f in g: g[f] = res(g[f])
for c in S["channels"].values(): c["commit"] = res(c["commit"])
for row in S["trunk"]: row[2] = res(row[2])
new_tags = {n: git("rev-parse", f"refs/tags/{n}").strip() for n in NEW_TAGS}
tags_txt = show(STATE_REF, "tags.txt").decode() + "".join(f"{s} refs/tags/{n}\n" for n, s in sorted(new_tags.items()))
top = {l.split("\t")[1]: l.split("\t")[0] for l in git("ls-tree", STATE_REF).splitlines()}
blob_sha = lambda data: git("hash-object", "-w", "--stdin", input=data).strip()
top["state.json"] = f"100644 blob {blob_sha(json.dumps(S, indent=0, sort_keys=True))}"
top["tags.txt"] = f"100644 blob {blob_sha(tags_txt)}"
tree = git("mktree", "--missing", input="".join(f"{v}\t{k}\n" for k, v in sorted(top.items())), check=True).strip()
env = dict(ENV, GIT_AUTHOR_NAME=AUTHOR_NAME, GIT_AUTHOR_EMAIL=AUTHOR_EMAIL, GIT_COMMITTER_NAME=AUTHOR_NAME, GIT_COMMITTER_EMAIL=AUTHOR_EMAIL)
state_new = subprocess.run(["git", "-C", R, "commit-tree", tree, "-p", git("rev-parse", STATE_REF).strip()],
                           input=f"sync through TUF targets v{NEWEST}\n\n{len(evs)} TUF versions, {len(new_tags)} new tags\n", capture_output=True, text=True, env=env, check=True).stdout.strip()

git("update-ref", "refs/heads/mirror-state", state_new)

# ---------------------------------------------------------------- 8. verify before pushing
fails = []
def check(ok, what):
    if not ok: fails.append(what)
for ev in evs:
    if ev["missing"]: continue
    c_ = new_tags[f"tuf/v{ev['version']}"]
    check(show(c_, "tuf/targets.json") == ev["raw"], f"targets.json v{ev['version']} not byte-identical")
    if ev["snap"]: check(show(c_, "tuf/snapshot.json") == ev["snap"], f"snapshot.json v{ev['version']} not byte-identical")
final_targets = json.loads(evs[-1]["raw"] if not evs[-1]["missing"] else show(main_new, "tuf/targets.json"))["signed"]["targets"]
touched = {k for ev in evs if not ev["missing"] for k in list(ev["added"]) + list(ev["changed"])}
paths = {}
for k in touched:
    name = k.rsplit("/", 1)[0]; b = parse_update_name(name)
    paths[k] = f"builds/F{b['milestone']:02d}/{b['version']}/{b['variant']}-{b['channel']}/PACKAGE.json" if b else f"named/{name}/PACKAGE.json"
tree_main = ls_tree(main_new, *sorted(paths.values())) if paths else {}
data = read_blobs(sorted(set(tree_main.values()))) if tree_main else {}
for k, pth in paths.items():
    check(pth in tree_main and json.loads(data[tree_main[pth]])["meta_far"]["merkle"] == final_targets[k]["custom"]["merkle"], f"main {pth} not at the newest target")
check(git("rev-parse", f"{main_new}^{{tree}}").strip() == git("rev-parse", f"{cond_new}^{{tree}}").strip(), "condensed tree differs from main")
for k, c in S["channels"].items():
    if c["commit"] in MARKS.values() or c["commit"] in new_tags.values():
        TREE_STATE.pop(c["commit"], None)
        pk, im, up = state_at(c["commit"])
        check(up.get(c["channel"]) == c["merkle"], f"{k}: update package at its channel commit is wrong")
        rec = rec_of(c["merkle"]); b = dict(parse_update_name(k.rsplit("/", 1)[0]), rec=rec, target=k, merkle=c["merkle"])
        kk = pins_of(b)
        if kk:
            check(pk == dict(kk[0]), f"{k}: pinned packages at its channel commit differ from packages.json")
            check({n: h for (c2, n), h in im.items() if c2 == c["channel"]} == dict(kk[1]), f"{k}: image packages differ from images.json")
authors = set(git("log", "--format=%an <%ae>|%cn <%ce>", f"{MAIN_BASE}..{main_new}").split("\n")) - {""}
check(int(git("rev-list", "--count", f"{state['condensed']}..{cond_new}")) == len(HAND) + sum(1 for e in evs if not e["missing"]) + 1, "condensed does not have one commit per publish")
check(authors <= {"Jared <77949461+ThePharmer@users.noreply.github.com>|Jared <77949461+ThePharmer@users.noreply.github.com>"}, f"unexpected authors {authors}")
if fails:
    for f in fails[:20]: log("FAIL", f)
    stop(f"{len(fails)} verification failures; nothing pushed")
log("verification passed")

# ---------------------------------------------------------------- 9. push (atomic, fast-forward only)
updates = {"refs/heads/main": main_new, "refs/heads/condensed": cond_new, "refs/heads/mirror-state": state_new}
for br, r_ in tips.items():
    updates["refs/heads/" + br] = res(r_)
updates = {r_: s for r_, s in updates.items() if REMOTE.get(r_) != s}
summary = {"tuf_from": LAST + 1, "tuf_to": NEWEST, "tuf_versions": len(evs), "new_build_versions": sum(1 for v in S["versions"] if v not in state["versions"]),
           "branches_updated": sorted(r_[11:] for r_ in updates if r_ in REMOTE),
           "branches_created": sorted(r_[11:] for r_ in updates if r_ not in REMOTE), "new_tags": len(new_tags),
           "late_channels": len(docs["late"]), "republished": len(docs["republished"]), "new_variants": len(docs["variants"]), "new_lines": len(docs["bases"])}
json.dump(summary, open(os.path.join(a.work, "summary.json"), "w"), indent=1)
log("summary", json.dumps(summary))
if a.dry_run:
    log("RESULT: dry run, nothing pushed"); sys.exit(0)
url = a.push_url or a.url
r = subprocess.run(["git", "-C", R, "push", "--atomic", "--no-verify", "-q", url] + [f"{s}:{r_}" for r_, s in sorted(updates.items())],
                   capture_output=True, text=True, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
if r.returncode: stop("push rejected (nothing was changed on GitHub): " + r.stderr[-1500:])
after = dict(l.split("\t")[::-1] for l in subprocess.run(["git", "ls-remote", url], capture_output=True, text=True).stdout.splitlines() if "\t" in l)
bad = [r_ for r_, s in updates.items() if after.get(r_) != s]
if bad: stop(f"after the push, {len(bad)} branches do not match: {bad[:5]}")
log(f"RESULT: pushed TUF v{LAST + 1}-v{NEWEST}, {len(updates)} branches updated; {len(new_tags)} new tags recorded in mirror-state:tags.txt")
