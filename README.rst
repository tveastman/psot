PS OVER TIME
============

This program parses the output of 'ps' and throws it into an sqlite3
database with a timestamp. The result is a simple data-capture utility
you can use to see the resource usage of any process over the lifetime
of that process.

Simple usage:
-------------

1. Set up data collection either as a cronjob running 'psot.py -m' at
   an interval of your choosing or run in 'daemon' mode where a measurement
   is taken every X minutes with 'psot.py -d X'.
2. Go on with your day.

Data retrieval:
---------------

This is very crude at the moment. Running 'psot.py' with no arguments
lists all the processes recorded with 'process_id', 'pid', 'process
start time' and the complete command line used to execute the process.
Note: process_id is the database ID that 'psot' uses -- not the PID.

Run 'psot.py 123', where '123' is the 'process_id' you're interested
in to get a dump of the recorded values. At the moment it's just the
raw data -- for the moment you have to handle your own graphing with
gnuplot or google visualizations or however you want to see your data.

Notes/TODOs:
------------

- By default, only processes that have been running longer than one
  minute are recorded in the database, this is configurable with the
  '--ignore=SECONDS' parameter.

- The database is stored in ${HOME}/.psot.sqlite3, this isn't
  configurable yet.

- The database grows pretty quickly -- a couple megabytes an hour
  depending on the number of processes you've got. Don't set it
  running then forget about it for weeks! Later I'll add the ability
  to purge old data.
