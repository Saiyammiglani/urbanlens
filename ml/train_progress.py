"""Live progress bar for the v2 training run.

Usage:  python train_progress.py          (Ctrl+C to stop)
Reads /tmp/train_v2.log (the training stdout) and redraws a bar out of 100%.
"""
import os
import re
import sys
import time

TOTAL_EPOCHS = 30
BATCHES = 1549
LOG = os.environ.get("TRAIN_LOG", "/tmp/train_v2.log")

EPOCH_RE = re.compile(rb"(\d+)/(\d+)\s+[\d.]+G\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+\d+\s+640.*?(\d+)/(\d+)")

# █ full blocks; ETA smoothing
EMA_RATE = None


def _log_candidates():
    yield os.environ.get("TRAIN_LOG", "")
    yield os.path.join(os.environ.get("TEMP", "/tmp"), "train_v2.log")  # Git Bash /tmp
    yield "/tmp/train_v2.log"
    yield os.path.join(os.path.dirname(os.path.abspath(__file__)), "train_v2.log")


def read_state():
    """Return (epoch, total_epochs, batch, total_batches, rate) or None."""
    global EMA_RATE
    data = None
    for path in _log_candidates():
        if not path:
            continue
        try:
            with open(path, "rb") as f:
                f.seek(max(0, os.path.getsize(path) - 400_000))  # tail only
                data = f.read()
            break
        except OSError:
            continue
    if data is None:
        return None
    matches = EPOCH_RE.findall(data)
    if not matches:
        return None
    e, te, b, tb = map(int, matches[-1])
    if te:
        TOTAL_EPOCHS = te
    rate = None
    m = re.search(rb"([\d.]+)it/s", data[-3000:])
    if m:
        r = float(m.group(1))
        EMA_RATE = r if EMA_RATE is None else 0.2 * r + 0.8 * EMA_RATE
        rate = EMA_RATE
    return e, te, b, tb, rate


def fmt_eta(seconds):
    if seconds is None or seconds <= 0 or seconds > 86400 * 2:
        return "--:--:--"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def render():
    st = read_state()
    if st is None:
        return "  waiting for training output..."
    e, te, b, tb, rate = st
    if te == 0:
        te = TOTAL_EPOCHS
    if tb == 0:
        tb = BATCHES
    frac = ((e - 1) + min(b, tb) / tb) / te
    pct = frac * 100
    width = 32
    filled = int(width * frac)
    bar = "█" * filled + "░" * (width - filled)
    # ETA: remaining batches this epoch + remaining epochs
    rem_batches = (tb - b) + (te - e) * tb
    eta = (rem_batches / rate) if rate else None
    return (f"\r  {bar} {pct:5.1f}%  epoch {e}/{te}  batch {b}/{tb}"
            f"  {rate or 0:.1f} it/s  ETA {fmt_eta(eta)}   ")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("UrbanLens v2 training progress  (Ctrl+C to exit)")
    try:
        last = ""
        while True:
            out = render()
            if out != last or out.startswith("\r"):
                sys.stdout.write(out)
                sys.stdout.flush()
                last = out
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
