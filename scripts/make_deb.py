#!/usr/bin/env python3
"""Builds a .deb with the standard library only (no dpkg-deb): ar with debian-binary, control.tar.gz and data.tar.gz.

usage: make_deb.py <data-root-folder> <control-file> <postinst> <output.deb>
"""

import hashlib
import io
import os
import sys
import tarfile
import time


def _tar_gz(members, compresslevel=9) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=compresslevel, format=tarfile.GNU_FORMAT) as tar:
        for info, data in members:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return buf.getvalue()


def _info(name, mode, kind=tarfile.REGTYPE, size=0, link=""):
    info = tarfile.TarInfo(name)
    info.mode, info.type, info.size, info.linkname = mode, kind, size, link
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    info.mtime = int(time.time())
    return info


def data_members(root):
    members, sums = [], []
    dirs_seen = set()
    for current, dirs, files in os.walk(root):
        dirs.sort()
        rel_dir = os.path.relpath(current, root).replace(os.sep, "/")  # name in the package: always with /, even when built on Windows
        if rel_dir != "." and rel_dir not in dirs_seen:
            dirs_seen.add(rel_dir)
            members.append((_info(f"./{rel_dir}/", 0o755, tarfile.DIRTYPE), None))
        for name in sorted(files) + sorted(d for d in dirs if os.path.islink(os.path.join(current, d))):
            path = os.path.join(current, name)
            rel = os.path.normpath(os.path.join(rel_dir, name)).replace(os.sep, "/")
            if os.path.islink(path):
                members.append((_info(f"./{rel}", 0o777, tarfile.SYMTYPE, link=os.readlink(path)), None))
                continue
            with open(path, "rb") as fh:
                data = fh.read()
            mode = 0o755 if os.access(path, os.X_OK) else 0o644
            members.append((_info(f"./{rel}", mode, size=len(data)), data))
            sums.append(f"{hashlib.md5(data).hexdigest()}  {rel}\n")
    return members, "".join(sums)


def ar_member(name: str, data: bytes) -> bytes:
    header = f"{name:<16}{int(time.time()):<12}{0:<6}{0:<6}{0o100644:<8o}{len(data):<10}`\n".encode("ascii")
    assert len(header) == 60
    return header + data + (b"\n" if len(data) % 2 else b"")


def main(root, control_path, postinst_path, out):
    members, md5sums = data_members(root)
    data_tar = _tar_gz(members)
    with open(control_path, "rb") as fh:
        control = fh.read()
    with open(postinst_path, "rb") as fh:
        postinst = fh.read()
    installed_kb = sum(len(d) for _i, d in members if d) // 1024 + 1
    control = control.replace(b"@SIZE@", str(installed_kb).encode())
    control_tar = _tar_gz([
        (_info("./", 0o755, tarfile.DIRTYPE), None),
        (_info("./control", 0o644, size=len(control)), control),
        (_info("./md5sums", 0o644, size=len(md5sums.encode())), md5sums.encode()),
        (_info("./postinst", 0o755, size=len(postinst)), postinst),
    ])
    with open(out, "wb") as fh:
        fh.write(b"!<arch>\n")
        fh.write(ar_member("debian-binary", b"2.0\n"))
        fh.write(ar_member("control.tar.gz", control_tar))
        fh.write(ar_member("data.tar.gz", data_tar))


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
