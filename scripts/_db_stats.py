"""Stats rapides tablebase — usage: python _db_stats.py <chemin_db>"""
import sqlite3
import sys

db = sys.argv[1]
c = sqlite3.connect(db)

def q(s):
    return c.execute(s).fetchone()[0]

print(q("select count(*) from positions"))
print(q("select count(*) from work_queue where status='pending'"))
print(q("select count(*) from work_queue where status='failed'"))
print(q("select count(*) from work_queue where status='in_progress'"))
