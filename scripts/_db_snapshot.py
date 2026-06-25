"""Snapshot compact de la base pour le monitoring : positions pending failed in_progress."""
import sqlite3
import sys

c = sqlite3.connect(sys.argv[1])


def q(s):
    return c.execute(s).fetchone()[0]


print(q("select count(*) from positions"))
print(q("select count(*) from work_queue where status='pending'"))
print(q("select count(*) from work_queue where status='failed'"))
print(q("select count(*) from work_queue where status='in_progress'"))
