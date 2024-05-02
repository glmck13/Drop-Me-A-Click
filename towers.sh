#!/bin/bash

DBDIR=~/drop-me-a-click
DBFILE=towers.db
CSVFILE=towers.csv
MCCLIST="310 311 312 313 314 315 316"

cd $DBDIR; rm -f $DBFILE $CSVFILE
. getenv.sh

for mcc in $MCCLIST
do
curl "${OPENCELLID_URL}?token=${UNWIRED_TOKEN}&type=mcc&file=${mcc}.csv.gz" | gzip -d  >>$CSVFILE
done

sqlite3 $DBFILE <<EOF
CREATE TABLE IF NOT EXISTS "towers"(
  "radio" TEXT,
  "mcc" TEXT,
  "net" TEXT,
  "area" TEXT,
  "cell" TEXT,
  "unit" TEXT,
  "lon" TEXT,
  "lat" TEXT,
  "range" TEXT,
  "samples" TEXT,
  "changeable" TEXT,
  "created" TEXT,
  "updated" TEXT,
  "averageSignal" TEXT
);
.mode csv
.import $CSVFILE towers
create index cell_index on towers (cell);
.exit
EOF

rm -f $CSVFILE
