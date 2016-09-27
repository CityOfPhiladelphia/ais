import sys
from subprocess import call

Engine_Scripts = [
                  "load_streets",
                  "load_street_aliases",
                  "load_opa_properties",
                  "load_dor_parcels",
                  "load_pwd_parcels",
                  "load_curbs",
                  "load_addresses",
                  "load_zip_ranges",
                  "geocode_addresses",
                  "make_address_summary",
                  "load_service_areas",
                  "make_service_area_summary"
                ]

for script in Engine_Scripts:
    try:
        print("starting running " + script)
        call("ais engine run " + script)
        print("finished running " + script)
    except Exception as e:
        print(sys.stderr, "failed")
        print(sys.stderr, "Exception: %s" % str(e))
        sys.exit(1)





