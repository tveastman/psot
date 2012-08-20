#!/usr/bin/env python

"""

PS OVER TIME
============

This program parses the output of 'ps' and throws it into an sqlite3
database with a timestamp. The result is a simple data-capture utility
you can use to see the resource usage of any process over the lifetime
of that process.

Simple usage:

1. Set up data collection either as a cronjob running 'psot.py -m' at
   an interval of your choosing or run in 'daemon' mode where a measurement
   is taken every X minutes with 'psot.py -d X'.
2. Go on with your day.

Data retrieval:

This is very crude at the moment. Running 'psot.py' with no arguments
lists all the processes recorded with 'process_id', 'pid', 'process
start time' and the complete command line used to execute the process.
Note: process_id is the database ID that 'psot' uses -- not the PID.

Run 'psot.py 123', where '123' is the 'process_id' you're interested
in to get a dump of the recorded values. At the moment it's just the
raw data -- for the moment you have to handle your own graphing with
gnuplot or google visualizations or however you want to see your data.

Notes/TODOs:

- By default, only processes that have been running longer than one
  minute are recorded in the database, this is configurable with the
  '--ignore=SECONDS' parameter.

- The database is stored in ${HOME}/.psot.sqlite3, this isn't
  configurable yet.

- The database grows pretty quickly -- a couple megabytes an hour
  depending on the number of processes you've got. Don't set it
  running then forget about it for weeks! Later I'll add the ability
  to purge old data.
"""

from time import sleep
import subprocess
import datetime
import logging
import optparse
import sqlite3
import pprint
import sys
import os


log = logging.getLogger()

def main():
    options, args = parse_options()
    init_logging(options.verbose)
    
    if options.measure:
        take_measurement(ignore=options.ignore)
    elif options.daemon:
        loop_forever(int(options.daemon), int(options.ignore))
    elif args:
        print_for_process(args[0])
    else:
        print_process_list()

def print_process_list():
    connection = get_database()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM process")
    for row in cursor.fetchall():
        print row['id'], row['pid'], row['lstart'], repr(row['cmd'])
    connection.close()

def print_for_process(process_id):
    connection = get_database()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM measurement WHERE process_id = ? ORDER BY timestamp", (process_id,))
    all = cursor.fetchall()
    keys = all[0].keys()
    print " ".join(keys)
    for row in all:
        print " ".join([str(row[i]) for i in keys])
    connection.close()

def loop_forever(waiting_time, ignore):
    while True:
        take_measurement(ignore)
        sleep(waiting_time * 60)

def take_measurement(ignore):
    connection = get_database()
    cur = connection.cursor()
    now = datetime.datetime.now()
    for row in parse_ps():
        if row['etime'] > int(ignore):
            insert_measurement(cur, row, now)
    connection.commit()
    connection.close()

    
def insert_measurement(cursor, row, now):
    cursor.execute("""INSERT OR IGNORE INTO 
                        process(lstart, pid, ppid, cmd)
                      VALUES (?, ?, ?, ?)""",
               (row['lstart'], row["pid"], row["ppid"], row["cmd"]))
    cursor.execute("""INSERT INTO measurement(process_id, timestamp, rss, thcount, size, 'group', vsz, cputime, etime, user, pmem) VALUES ((SELECT id FROM process WHERE pid = ? AND lstart = ? AND cmd = ?), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            row["pid"],  row["lstart"], row["cmd"], now, 
            row["rss"],
            row["thcount"],
            row["size"],
            row["group"],
            row["vsz"],
            row["cputime"],
            row["etime"],
            row["user"],
            row["pmem"]))


def get_database():
    connection = sqlite3.connect(os.path.join(os.environ["HOME"], ".psot.sqlite3"),
                                 detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    connection.row_factory = sqlite3.Row
    connection.execute("""
       CREATE TABLE IF NOT EXISTS process (
         id INTEGER PRIMARY KEY,
         ppid INTEGER,
         pid INTEGER,
         lstart TIMESTAMP,
         cmd TEXT,
         CONSTRAINT pid_lstart_cmd_unique UNIQUE (pid, lstart, cmd))
    """)
    connection.execute("""
       CREATE TABLE IF NOT EXISTS measurement (
         process_id INTEGER,
         timestamp timestamp,
         rss INTEGER,
         thcount INTEGER,
         size INTEGER,
         "group" TEXT,
         vsz INTEGER,
         cputime INTEGER,
         etime INTEGER,
         user TEXT,
         pmem NUMERIC,
         FOREIGN KEY(process_id) REFERENCES process(id))
    """)
    connection.execute("""
       CREATE INDEX IF NOT EXISTS measurement_ps_date_idx ON measurement (process_id, timestamp)
    """)
    return connection
    
    
         

def parse_ps():
    """Execute 'ps', parse the output, and return it as a dictionary."""
    ## The list of fields we want to collect, and how many fields it consists of
    fields = [
        ("cputime", 1),
        ("etime", 1),
        ("rss", 1),
        ("vsz", 1),
        ("size", 1),
        ("pmem", 1),
        ("user", 1),
        ("group", 1),
        ("thcount", 1),
        ("ppid", 1),
        ## required
        ("pid", 1),
        ("lstart", 5),
        ## This one must be last
        ("cmd", None),
        ]
    slices, max_split = get_slices(fields)
    output = subprocess.Popen(["ps", "-ewwo", ",".join(f[0] for f in fields)],
                              stdout=subprocess.PIPE).communicate()[0]
    rows = []
    for line in output.split("\n")[1:]:
        if not line: continue
        tokens = line.split(None, max_split)
        row = {}
        for f in slices:
            row[f] = tokens[slices[f]]
        ## Do conversions on data in the fields
        row["etime"] = convert_ps_time(row["etime"])
        row["cputime"] = convert_ps_time(row["cputime"])
        row["cmd"] = row["cmd"][0].strip()
        row["lstart"] = datetime.datetime.strptime(" ".join(row["lstart"]), 
                                                   "%a %b %d %H:%M:%S %Y")
        ##

        rows.append(row)
    return rows

def convert_ps_time(string):
    """Convert the 'time' type fields from D-HH:MM:SS to seconds"""
    split = string.split(":")
    if len(split) == 3:
        hours, minutes, seconds = split
    else:
        hours, minutes, seconds = ["0"] + split
    if "-" in hours:
        days, hours = hours.split("-")
    else:
        days = 0
    return (int(seconds) +
            int(minutes) * 60 +
            int(hours) * 60 * 60 +
            int(days) * 24 * 60 * 60)
        
def get_slices(fields):
    start = 0
    slices = {}
    for i in fields:
        length = i[1]
        if length == 1:
            s = start
            start += 1
        elif length is not None:
            s = slice(start, start + length)
            start += length
        else:
            s = slice(start, None)
        slices[i[0]] = s
    return slices, start
        

def init_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level,
                        format='%(levelname)8s %(message)s')

def parse_options():
    parser = optparse.OptionParser(usage=__doc__)
    parser.add_option("-v", "--verbose", default=False)
    parser.add_option("-m", "--measure", default=False, action="store_true",
                      help="Take a measurement then exit")
    parser.add_option("-d", "--daemon", default=0,
                      help="Run indefinitely, taking a measurement every X minutes", 
                      metavar="MINUTES")
    parser.add_option("-i", "--ignore", default=60,
                      help="Ignore processes younger than SECONDS. Default %(default)s", 
                      metavar="SECONDS")
    parsed_options, parsed_args = parser.parse_args()
    return parsed_options, parsed_args


if __name__ == "__main__": main()
