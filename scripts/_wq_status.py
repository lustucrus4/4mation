import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
for row in c.execute("select status, count(*) from work_queue group by status"):
    print(f"{row[0]}: {row[1]}")
