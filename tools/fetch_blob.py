#!/usr/bin/env python3
"""Fetch the bytes behind one or more *.ptr.json pointer files and verify them.

usage: fetch_blob.py POINTER.ptr.json [...] [-o OUTDIR]

- kind "blob": downloads the blob and checks its Fuchsia merkle root.
- kind "far-entry": downloads the meta.far, checks its merkle root, extracts the entry and checks its sha256.
Output files are written next to the pointer (without the .ptr.json suffix) unless -o is given.
No third-party packages needed.
"""
import argparse, hashlib, json, os, struct, sys, urllib.request

BLOCK = 8192
FAR_MAGIC = b"\xc8\xbf\x0b\x48\xad\xab\xc5\x11"


def merkle_root(data):
    def h(ident, length, blk):
        return hashlib.sha256(struct.pack("<QI", ident, length) + blk + b"\0" * (BLOCK - len(blk))).digest()
    if not data:
        return hashlib.sha256(b"\0" * 12).hexdigest()
    hs = [h(o, len(data[o:o + BLOCK]), data[o:o + BLOCK]) for o in range(0, len(data), BLOCK)]
    level = 1
    while len(hs) > 1:
        cat = b"".join(hs)
        hs = [h(o | level, BLOCK, cat[o:o + BLOCK]) for o in range(0, len(cat), BLOCK)]
        level += 1
    return hs[0].hex()


def far_entry(buf, path):
    if buf[:8] != FAR_MAGIC:
        raise ValueError("not a FAR archive")
    (index_len,) = struct.unpack_from("<Q", buf, 8)
    chunks = {}
    for i in range(index_len // 24):
        ctype, off, ln = struct.unpack_from("<8sQQ", buf, 16 + i * 24)
        chunks[ctype] = (off, ln)
    doff, dlen = chunks[b"DIR-----"]
    noff, nlen = chunks[b"DIRNAMES"]
    names = buf[noff:noff + nlen]
    for i in range(dlen // 32):
        name_off, name_len, _r, data_off, data_len, _r2 = struct.unpack_from("<IHHQQQ", buf, doff + i * 32)
        if names[name_off:name_off + name_len].decode() == path:
            return buf[data_off:data_off + data_len]
    raise KeyError(path)


def download(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pointers", nargs="+")
    ap.add_argument("-o", "--outdir")
    a = ap.parse_args()
    for ptr_path in a.pointers:
        p = json.load(open(ptr_path))
        if p.get("kind") == "blob":
            data = download(p["url"])
            if merkle_root(data) != p["merkle"]:
                sys.exit(f"{ptr_path}: merkle mismatch, refusing to write")
        elif p.get("kind") == "far-entry":
            far = download(p["far_url"])
            if merkle_root(far) != p["far_merkle"]:
                sys.exit(f"{ptr_path}: meta.far merkle mismatch, refusing to write")
            data = far_entry(far, p["path"])
            if hashlib.sha256(data).hexdigest() != p["sha256"]:
                sys.exit(f"{ptr_path}: entry sha256 mismatch, refusing to write")
        else:
            sys.exit(f"{ptr_path}: unknown pointer kind {p.get('kind')!r}")
        name = os.path.basename(ptr_path)[: -len(".ptr.json")]
        dest = os.path.join(a.outdir or os.path.dirname(ptr_path) or ".", name)
        with open(dest, "wb") as f:
            f.write(data)
        print(f"{dest}: {len(data)} bytes, verified")


if __name__ == "__main__":
    main()
