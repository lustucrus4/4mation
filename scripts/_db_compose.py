"""Composition de la base pour decision compaction — usage: python _db_compose.py <db>"""
import os
import sqlite3
import sys

db = sys.argv[1]
c = sqlite3.connect(db)


def q(s):
    return c.execute(s).fetchone()[0]


size = sum(
    os.path.getsize(db + suf)
    for suf in ("", "-wal", "-shm")
    if os.path.exists(db + suf)
)
print(f"Taille disque : {size / 1e9:.2f} Go")

print(f"positions            : {q('select count(*) from positions')}")
print(f"work_queue total     : {q('select count(*) from work_queue')}")
for st in ("pending", "in_progress", "done", "failed"):
    n = q("select count(*) from work_queue where status='" + st + "'")
    print(f"  wq {st:12s}: {n}")

avg_pos = q("select avg(length(board_json)) from positions where board_json is not null")
avg_wq = q("select avg(length(board_json)) from work_queue")
print(f"avg board_json positions  : {avg_pos:.0f} octets" if avg_pos else "avg positions: n/a")
print(f"avg board_json work_queue : {avg_wq:.0f} octets" if avg_wq else "avg work_queue: n/a")
