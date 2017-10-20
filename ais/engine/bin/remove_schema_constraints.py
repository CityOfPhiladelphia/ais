import sys, json

json_file = sys.argv[1]

with open(json_file) as infile:
    data = json.load(infile)

def fixup(adict, k, v):
    for key in adict.keys():
        if key == k:
            adict[key] = v
        elif type(adict[key]) is dict:
            fixup(adict[key], k, v)
for el in data['fields']:
    fixup(el, "required", False)

with open(json_file, 'w') as outfile:
    json.dump(data, outfile)