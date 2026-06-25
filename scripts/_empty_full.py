import json
import sqlite3
import sys

c = sqlite3.connect(sys.argv[1])
counts = {}
total = 0
for (bj,) in c.execute("select board_json from positions"):
    b = json.loads(bj)
    e = sum(1 for row in b for cell in row if cell == 0)
    counts[e] = counts.get(e, 0) + 1
    total += 1
print(f"TOTAL = {total}")
for e in sorted(counts):
    print(f"empty={e}: {counts[e]}")
