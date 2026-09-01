"""Robust chunked range downloader for FigShare members (resumable, retrying).

Reads the exact data offset from each member's local zip header, then pulls the
payload in 32 MB chunks with curl (which retries/resumes), concatenating parts.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import requests
from remotezip import RemoteZip

URL = "https://ndownloader.figshare.com/files/38030910"
CHUNK = 32 * 1024 * 1024
OUT = Path(__file__).parent / "datasets" / "downloads"


def member_data_offset(url: str, header_offset: int) -> int:
    """Local file header: 30 bytes + fname + extra. Read it via one range req."""
    import struct
    r = requests.get(url, headers={"Range": f"bytes={header_offset}-{header_offset + 63}"}, timeout=60)
    r.raise_for_status()
    (sig, _ver, _flags, _method, _t, _d, _crc, _comp, _uncomp,
     fn_len, extra_len) = struct.unpack("<IHHHHHIIIHH", r.content[:30])
    assert sig == 0x04034B50, f"bad local header sig at {header_offset}"
    start = header_offset + 30 + fn_len + extra_len
    # verify: first 4 bytes of payload must be PK\x03\x04 (inner zip)
    chk = requests.get(url, headers={"Range": f"bytes={start}-{start + 3}"}, timeout=60)
    assert chk.content[:4] == b"PK\x03\x04", f"payload magic mismatch: {chk.content[:4].hex()}"
    return start


def curl_range(url: str, start: int, end: int, dest: Path, tries: int = 6) -> bool:
    rng = f"{start}-{end}"
    for attempt in range(1, tries + 1):
        p = subprocess.run(
            ["curl", "-sL", "--fail", "--retry", "3", "--retry-delay", "2",
             "--speed-limit", "10000", "--speed-time", "30",
             "-r", rng, "-o", str(dest), url],
            capture_output=True, text=True,
        )
        if p.returncode == 0 and dest.exists() and dest.stat().st_size == end - start + 1:
            return True
        print(f"  chunk {rng} attempt {attempt} failed (rc={p.returncode}, got "
              f"{dest.stat().st_size if dest.exists() else 0} bytes), retrying...")
        time.sleep(3 * attempt)
    return False


def fetch(name: str, header_offset: int, size: int) -> bool:
    dest = OUT / name.replace(".zip", "_RDD.zip")
    if dest.exists() and dest.stat().st_size == size:
        print(f"[skip] {dest.name} complete")
        return True
    data_start = member_data_offset(URL, header_offset)
    total_end = data_start + size - 1
    print(f"[get ] {name}: {size/1e6:.0f} MB from byte {data_start}")

    tmp = dest.with_suffix(".part")
    pos = data_start
    if tmp.exists():
        pos = data_start + tmp.stat().st_size  # resume
        print(f"  resuming at {(pos - data_start) / 1e6:.0f} MB")
    chunk_n = 0
    while pos <= total_end:
        end = min(pos + CHUNK - 1, total_end)
        part = OUT / f".chunk_{chunk_n}"
        if not curl_range(URL, pos, end, part):
            print(f"[FAIL] chunk at {pos}")
            return False
        with tmp.open("ab") as t, part.open("rb") as p:
            while True:
                buf = p.read(1 << 20)
                if not buf:
                    break
                t.write(buf)
        part.unlink()
        pos = end + 1
        chunk_n += 1
        print(f"  {min((pos-data_start)/size*100, 100):5.1f}%  ({(pos-data_start)/1e6:.0f}/{size/1e6:.0f} MB)")
    if tmp.stat().st_size == size:
        tmp.rename(dest)
        print(f"[done] {dest.name}")
        return True
    print(f"[FAIL] size mismatch {tmp.stat().st_size} != {size}")
    return False


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with RemoteZip(URL) as z:
        members = {i.filename.split("/")[-1]: i for i in z.infolist()}
    for name in ("India.zip", "Japan.zip", "Czech.zip"):
        info = members[name]
        ok = fetch(name, info.header_offset, info.compress_size)
        if not ok:
            sys.exit(1)
    print("ALL COUNTRY ZIPS FETCHED")


if __name__ == "__main__":
    main()
