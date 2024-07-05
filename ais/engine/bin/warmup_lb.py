import petl as etl
import psycopg2
import time
from datetime import datetime
import requests
import sys, os
import click


@click.command()
@click.option('--proxy', '-p', required=False,
              help='proxy is only necessary when run from the office')
@click.option('--dbpass', '-dp', required=True,
              help='')
@click.option('--gatekeeper-key', '-k', required=True,
              help='')
def main(proxy, dbpass, gatekeeper_key):
    base_path = 'http://api.phila.gov/ais_staging/v1/search/'

    warmup_address_table_name = 'address_summary'
    warmup_address_field = 'street_address'
    warmup_row_limit = 1000
    warmup_fraction_success = .9
    rate_limit = 5
    query_errors = {}

    datestamp = datetime.today().strftime('%Y-%m-%d')
    log_directory= os.path.join(os.getcwd(), 'log/')
    os.makedirs(log_directory, exist_ok=True)
    warmup_lb_error_file = log_directory + f'/warmup_lb_error-{datestamp}.txt'

    def RateLimited(maxPerSecond):
        minInterval = 1.0 / float(maxPerSecond)

        def decorate(func):
            lastTimeCalled = [0.0]

            def rateLimitedFunction(*args, **kargs):
                elapsed = time.process_time() - lastTimeCalled[0]
                leftToWait = minInterval - elapsed
                if leftToWait > 0:
                    time.sleep(leftToWait)
                ret = func(*args, **kargs)
                lastTimeCalled[0] = time.process_time()

                return ret
            return rateLimitedFunction
        return decorate



    from json.decoder import JSONDecodeError
    @RateLimited(rate_limit)
    def query_address(address):
        try:
            encoded_address = requests.utils.quote(address)
            url = base_path + encoded_address + '?' + gatekeeper_key
            #print(url)
            if proxy:
                proxies = { 'http': proxy,
                        'htps': proxy }
                r = requests.get(url, proxies=proxies, timeout=5)
            else:
                r = requests.get(url, timeout=5)
            if r.status_code:
                if int(r.status_code) != 200:
                    print(f"Got a non-200 status code for {url}!: {r.status_code}")
                return r.status_code
            else:
                return None
        except requests.exceptions.HTTPError as e:
            error = [e,'','']
            query_errors[url] = error
        except requests.exceptions.RequestException as e:
            error = [e,'','']
            query_errors[url] = error
        except JSONDecodeError as e:
            error = [e, r.raw.data, r.raw.read(100)]
            query_errors[url] = error


    read_conn = psycopg2.connect(f"dbname=ais_engine host=localhost user=ais_engine password={dbpass}")
    address_count = etl.fromdb(read_conn, 'select count(*) as N from {}'.format(warmup_address_table_name))
    n = list(address_count.values('n'))[0]
    warmup_rows = etl.fromdb(read_conn, 'select {address_field} from {table} OFFSET floor(random()*{n}) limit {limit}'.format(address_field=warmup_address_field, table=warmup_address_table_name, n=n, limit=warmup_row_limit))
    # print(etl.look(warmup_rows))
    responses = warmup_rows.addfield('response_status', (lambda a: query_address(a['street_address']))).progress(100)
    #print(etl.look(responses))
    eval = responses.aggregate('response_status', len)
    #print(etl.look(eval))

    # count the amount of successful hits
    f_200 = [(count/warmup_row_limit) for status, count in eval[1:] if (status == 200 and eval)]
    
    #print(f_200)
    ###########################
    # WRITE ERRORS OUT TO FILE #
    ############################
    print("Writing errors to file...")
    error_table = []
    for url, error_vals in query_errors.items():
        error_table.append([url, error_vals[0], error_vals[1]])
    etl.tocsv(error_table, warmup_lb_error_file)

    if f_200:
        # Compare the count against our limit of what we want to have succeeded
        if f_200[0] > warmup_fraction_success:
            exit(0)
        else:
            print('Too many failures encountered during warmup!')
            exit(1)
    else:
        print('Unable to count successes for some reason?')
        exit(1)



if __name__ == '__main__':
    main()
