# -*- coding: utf-8 -*-
"""Synthetic-motion unit test for RashDetector: a fast weaving vehicle must be
flagged; a steady vehicle must not."""
from rash_detector import RashDetector

rd = RashDetector("http://127.0.0.1:8000", "sih-demo-token")

# steady vehicle: moves right at 10 px/s, no lane changes
flagged_steady = False
for i in range(20):
    x = 100 + i * 2
    ev = rd.observe([(x, 200, x + 80, 280, "car")], now=i * 0.2)
    if ev:
        flagged_steady = True
print("steady vehicle flagged:", flagged_steady, "(expect False)")

# fast weaving vehicle: 150 px/s with direction flips every 2 frames
rd2 = RashDetector("http://127.0.0.1:8000", "sih-demo-token")
flagged_weaver = None
x = 100.0
for i in range(20):
    dx = 30 if (i // 2) % 2 == 0 else -30   # weave: +/-30px per 0.2s frame
    x += dx
    ev = rd2.observe([(x, 200, x + 80, 280, "car")], now=i * 0.2)
    if ev:
        flagged_weaver = ev
        break
print("weaving vehicle flagged:", bool(flagged_weaver), "(expect True)")
if flagged_weaver:
    print("evidence:", flagged_weaver)

# fast straight vehicle (no weaving) vs fleet median
rd3 = RashDetector("http://127.0.0.1:8000", "sih-demo-token")
flagged_speeder = None
for i in range(20):
    # fleet: slow cars at 5px/frame; suspect at 40px/frame
    cars = [(100 + i * 5, 300, 160 + i * 5, 360, "car"),
            (300 + i * 5, 300, 360 + i * 5, 360, "car"),
            (500 + i * 40, 100, 580 + i * 40, 180, "car")]
    ev = rd3.observe(cars, now=i * 0.2)
    if ev:
        flagged_speeder = ev
        break
print("speeder flagged:", bool(flagged_speeder), "(expect True)")
if flagged_speeder:
    print("evidence:", flagged_speeder)
