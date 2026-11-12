"""Crew lane locks and the free-RAM floor. Stdlib only.

Locks live in the main checkout (.crew/locks) so every worktree shares one heavy lane.
A lock older than 20 minutes is stale and can be taken.
Take creates the lock with O_EXCL. Release only clears a live lock when
ROOKERY_SUPER matches the owner stored at take time. Unset matches unset.
"""
import ctypes
import json
import os
import sys
import time
from pathlib import Path

STALE_S = 20 * 60
FLOOR = 2 * 1024**3


def main_root():
    here = Path(__file__).resolve().parents[1]
    git = here / ".git"
    if git.is_file():
        gitdir = Path(git.read_text(encoding="utf-8").split(":", 1)[1].strip())
        if gitdir.parent.name == "worktrees":
            return gitdir.parent.parent.parent
    return here


LOCKS = main_root() / ".crew" / "locks"


def free_bytes():
    class Mem(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    mem = Mem()
    mem.dwLength = ctypes.sizeof(Mem)
    fn = ctypes.windll.kernel32.GlobalMemoryStatusEx
    fn.argtypes = [ctypes.POINTER(Mem)]
    fn.restype = ctypes.c_int
    if not fn(ctypes.byref(mem)):
        raise OSError("GlobalMemoryStatusEx failed")
    return int(mem.ullAvailPhys)


def lane_ok(lane):
    return bool(lane) and all(c.isalnum() or c in "-_" for c in lane)


def lock_path(lane):
    return LOCKS / f"{lane}.json"


def read_lock(lane):
    path = lock_path(lane)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["stale"] = time.time() - float(data["ts"]) > STALE_S
        return data
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"lane": lane, "what": "unreadable", "ts": 0, "stale": True}


def cmd_free():
    n = free_bytes()
    print(f"free RAM: {n / 1024**3:.2f} GB")
    if n < FLOOR:
        print("below 2 GB floor")
        return 1
    return 0


def caller():
    return os.environ.get("ROOKERY_SUPER", "").strip() or "unset"


def exclusive_write(path, payload):
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


def cmd_take(lane, what):
    if not lane_ok(lane):
        print("bad lane name")
        return 2
    LOCKS.mkdir(parents=True, exist_ok=True)
    path = lock_path(lane)
    payload = json.dumps(
        {"lane": lane, "what": what, "owner": caller(), "ts": time.time()}
    ).encode("utf-8")
    for _ in range(8):
        try:
            exclusive_write(path, payload)
        except FileExistsError:
            cur = read_lock(lane)
            if cur is None:
                continue
            if not cur["stale"]:
                print(f"busy: {lane}: {cur['what']}")
                return 1
            token = path.with_name(f"{lane}.dead-{os.getpid()}-{time.time_ns()}")
            try:
                os.replace(path, token)
            except OSError:
                continue
            try:
                exclusive_write(path, payload)
            except FileExistsError:
                token.unlink(missing_ok=True)
                continue
            token.unlink(missing_ok=True)
        print(f"took {lane}: {what}")
        return 0
    print(f"busy: {lane}")
    return 1


def cmd_release(lane):
    if not lane_ok(lane):
        print("bad lane name")
        return 2
    path = lock_path(lane)
    cur = read_lock(lane)
    if cur and not cur["stale"] and (cur.get("owner") or "unset") != caller():
        print(f"not owner: {lane} held by {cur.get('owner')}")
        return 1
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    print(f"released {lane}")
    return 0


def cmd_status():
    if not LOCKS.exists():
        print("no locks")
        return 0
    rows = sorted(LOCKS.glob("*.json"))
    if not rows:
        print("no locks")
        return 0
    for path in rows:
        lane = path.stem
        data = read_lock(lane)
        age = time.time() - float(data["ts"])
        mark = " stale" if data["stale"] else ""
        print(f"{lane}: {data['what']} owner={data.get('owner') or 'unset'} ({age:.0f}s){mark}")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print('usage: slot.py take <lane> "<what>" | release <lane> | status | free')
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "free" and not rest:
        return cmd_free()
    if cmd == "status" and not rest:
        return cmd_status()
    if cmd == "release" and len(rest) == 1:
        return cmd_release(rest[0])
    if cmd == "take" and len(rest) == 2:
        return cmd_take(rest[0], rest[1])
    print('usage: slot.py take <lane> "<what>" | release <lane> | status | free')
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
