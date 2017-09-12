import petl as etl
import psycopg2
import time
import requests
import geopetl

base_path = 'http://api.phila.gov/ais_staging/v1/addresses/'
gatekeeper_key = 'gatekeeperKey=4b1dba5f602359a4c6d5c3ed731bfb5b'
warmup_address_table_name = 'address_summary'
warmup_address_field = 'street_address'
warmup_row_limit = 4000
warmup_fraction_success = .9
rate_limit = 3
query_errors = {}

def RateLimited(maxPerSecond):
    minInterval = 1.0 / float(maxPerSecond)

    def decorate(func):
        lastTimeCalled = [0.0]

        def rateLimitedFunction(*args, **kargs):
            elapsed = time.clock() - lastTimeCalled[0]
            leftToWait = minInterval - elapsed
            if leftToWait > 0:
                time.sleep(leftToWait)
            ret = func(*args, **kargs)
            lastTimeCalled[0] = time.clock()

            return ret
        return rateLimitedFunction
    return decorate



from json.decoder import JSONDecodeError
# @RateLimited(rate_limit)
def query_address(address):
    try:
        url = base_path + address + '?' + gatekeeper_key
        # print(url)
        r = requests.get(url)
        return r.status_code
    except requests.exceptions.HTTPError as e:
        error = [e,'','']
        query_errors[url] = error
    except requests.exceptions.RequestException as e:
        error = [e,'','']
        query_errors[url] = error
    except JSONDecodeError as e:
        error = [e, r.raw.data, r.raw.read(100)]
        query_errors[url] = error


read_conn = psycopg2.connect("dbname=ais_engine_test user=ais_engine")
address_count = etl.fromdb(read_conn, 'select count(*) as N from {}'.format(warmup_address_table_name))
n = list(address_count.values('n'))[0]
warmup_rows = etl.fromdb(read_conn, 'select {address_field} from {table} OFFSET floor(random()*{n}) limit {limit}'.format(address_field=warmup_address_field, table=warmup_address_table_name, n=n, limit=warmup_row_limit))
# print(etl.look(warmup_rows))
responses = warmup_rows.addfield('response_status', (lambda a: query_address(a['street_address']))).progress(100)
# print(etl.look(responses))
eval = responses.aggregate('response_status', len)
print(etl.look(eval))
f_200 = [(count/warmup_row_limit) for status, count in eval[1:] if status == 200][0]
print(f_200)
exit(0) if f_200 > warmup_fraction_success else exit(1)



