"""Fuchsia archive (FAR) reader and Fuchsia merkle-root calculator. No third-party deps.
Merkle per fuchsia.dev/fuchsia-src/concepts/packages/merkleroot, verified against its test vectors."""
import struct, hashlib

FAR_MAGIC = b"\xc8\xbf\x0b\x48\xad\xab\xc5\x11"
BLOCK = 8192

def parse_far(buf):
    if buf[:8] != FAR_MAGIC:
        raise ValueError("not a FAR")
    (index_len,) = struct.unpack_from("<Q", buf, 8)
    chunks = {}
    for i in range(index_len // 24):
        ctype, off, ln = struct.unpack_from("<8sQQ", buf, 16 + i * 24)
        chunks[ctype] = (off, ln)
    doff, dlen = chunks[b"DIR-----"]
    noff, nlen = chunks[b"DIRNAMES"]
    names = buf[noff:noff + nlen]
    entries = {}
    for i in range(dlen // 32):
        name_off, name_len, _r, data_off, data_len, _r2 = struct.unpack_from("<IHHQQQ", buf, doff + i * 32)
        entries[names[name_off:name_off + name_len].decode("utf-8")] = buf[data_off:data_off + data_len]
    return entries

def _h(ident, length, blk):
    return hashlib.sha256(struct.pack("<QI", ident, length) + blk + b"\0" * (BLOCK - len(blk))).digest()

def merkle_root(data):
    if not data:
        return hashlib.sha256(b"\0" * 12).hexdigest()
    hs = [_h(o, len(data[o:o + BLOCK]), data[o:o + BLOCK]) for o in range(0, len(data), BLOCK)]
    level = 1
    while len(hs) > 1:
        cat = b"".join(hs)
        hs = [_h(o | level, BLOCK, cat[o:o + BLOCK]) for o in range(0, len(cat), BLOCK)]
        level += 1
    return hs[0].hex()

def parse_contents(text):
    out = {}
    for line in text.decode("utf-8").splitlines():
        if "=" in line:
            path, m = line.rsplit("=", 1)
            out[path] = m
    return out
