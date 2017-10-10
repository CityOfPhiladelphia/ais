import sys
import csv

infile = sys.argv[1]
outfile = sys.argv[2]

reader = csv.reader(open(infile, "rt"), delimiter = ',')
writer = csv.writer(open(outfile, 'w', newline=''))
out_rows = []
for row in reader:
    out_rows.append([
        "".join(a if ord(a) < 128 else '' for a in i)
        for i in row
    ])
writer.writerows(out_rows)



