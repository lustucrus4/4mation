"""Remet in_progress en pending avant un test."""
import sqlite3
import sys

db = sys.argv[1]
c = sqlite3.connect(db)
n = c.execute(
    """UPDATE work_queue SET status='pending', worker_id=NULL, claimed_at=NULL
       WHERE status='in_progress'"""
).rowcount
c.commit()
print(n)
