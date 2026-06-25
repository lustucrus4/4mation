"""Distribution cases vides des positions pending."""
import json
import sqlite3
import sys

c = sqlite3.connect(sys.argv[1])
rows = c.execute(
    "select board_json from work_queue where status='pending' limit 500"
).fetchall()
counts = {}
for (bj,) in rows:
    b = json.loads(bj)
    empty = sum(1 for row in b for cell in row if cell == 0)
    counts[empty] = counts.get(empty, 0) + 1
for k in sorted(counts):
    print(f"empty={k}: {counts[k]}")
