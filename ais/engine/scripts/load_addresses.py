from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime
import multiprocessing
import os

from ais import app
from ais.engine.db import connect
from ais.util import parity_for_num, parity_for_range

# SET UP LOGGING / QC
street_warning_map = {}  # street_address => [{reason, notes}]
street_error_map = {}  # street_address => {reason, notes}

# Worker-process globals inherited copy-on-write via fork() on Linux
_WORKER_PARSER = None
_WORKER_PARSER_TAGS = ()

_PARALLEL_PARSE_THRESHOLD = 4000


@dataclass(slots=True)
class FastAddress:
    """Lightweight slotted equivalent of ais.models.Address for bulk engine loads.

    Avoids SQLAlchemy ORM instrumentation overhead on millions of rows while
    preserving identical validation, fields, and derived properties.
    """

    base_address: str | None
    address_low: int
    address_low_suffix: str | None
    address_low_frac: str | None
    address_high: int | None
    street_predir: str | None
    street_name: str
    street_suffix: str | None
    street_postdir: str | None
    unit_type: str | None
    unit_num: str | None
    floor: str | None
    street_full: str | None
    street_address: str | None
    zip_code: str | None
    zip_4: str | None

    @property
    def parity(self) -> str:
        if self.address_high:
            return parity_for_range(self.address_low, self.address_high)
        return parity_for_num(self.address_low)

    @property
    def address_full(self) -> str:
        address_full = str(self.address_low)
        if self.address_low_suffix:
            address_full += self.address_low_suffix
        if self.address_high:
            address_full += '-' + str(self.address_high)[-2:]
        if self.address_low_frac:
            address_full += ' ' + self.address_low_frac
        return address_full

    @property
    def address_full_num(self) -> str:
        num = str(self.address_low)
        if self.address_high:
            address_high = str(self.address_high)
            if len(address_high) < 2:
                num += '-' + address_high
            else:
                num += '-' + address_high[-2:]
        return num

    @property
    def base_address_no_suffix(self) -> str:
        return f'{self.address_full_num} {self.street_full}'

    @property
    def is_base(self) -> bool:
        return not (self.unit_type or self.address_low_suffix)

    @property
    def generic_unit(self) -> str:
        if self.unit_type is None:
            return self.street_address
        return ' '.join(
            x for x in (self.address_full, self.street_full, '#', self.unit_num) if x
        )

    @property
    def hundred_block(self) -> int:
        return self.address_low - (self.address_low % 100)

    @property
    def unit_full(self) -> str | None:
        if self.unit_type:
            if self.unit_num:
                return f'{self.unit_type} {self.unit_num}'
            return self.unit_type
        return None

    def as_dict(self) -> dict:
        return {
            'base_address': self.base_address,
            'address_low': self.address_low,
            'address_low_suffix': self.address_low_suffix,
            'address_low_frac': self.address_low_frac,
            'address_high': self.address_high,
            'street_predir': self.street_predir,
            'street_name': self.street_name,
            'street_suffix': self.street_suffix,
            'street_postdir': self.street_postdir,
            'unit_type': self.unit_type,
            'unit_num': self.unit_num,
            'floor': self.floor,
            'street_full': self.street_full,
            'street_address': self.street_address,
            'zip_code': self.zip_code,
            'zip_4': self.zip_4,
        }


def build_fast_address(parsed: dict, *, distinguish_none_type: bool = True) -> FastAddress | str:
    """Validate a Passyunk parse dict and return a FastAddress or error reason string."""
    addr_type = parsed['type']
    if distinguish_none_type and addr_type == 'none':
        return 'Unknown address type'
    if addr_type not in ('address', 'street'):
        return 'Not an address'

    c = parsed['components']
    street = c['street']
    addr = c['address']
    if street['name'] is None:
        return 'No street name'
    if addr['low'] is None:
        return 'No address low'

    low_num = addr['low_num']
    high_num_full = addr['high_num_full']
    if high_num_full and low_num and high_num_full < low_num:
        return 'Invalid range address'

    unit = c['address_unit']
    mailing = c['mailing']
    return FastAddress(
        base_address=c['base_address'],
        address_low=low_num,
        address_low_suffix=addr['addr_suffix'],
        address_low_frac=addr['fractional'],
        address_high=high_num_full,
        street_predir=street['predir'],
        street_name=street['name'],
        street_suffix=street['suffix'],
        street_postdir=street['postdir'],
        unit_type=unit['unit_type'],
        unit_num=unit['unit_num'],
        floor=c['floor']['floor_num'],
        street_full=street['full'],
        street_address=c['output_address'],
        zip_code=mailing['zipcode'],
        zip_4=mailing['zip4'],
    )


def extract_parser_tags(
    parsed: dict, parser_tags_items: tuple[tuple[str, tuple[str, ...]], ...]
) -> list[tuple[str, str, str]]:
    """Extract (street_address, key, value) parser tag triples from a Passyunk result."""
    comps = parsed.get('components')
    if not comps:
        return []
    street_address = comps.get('output_address', '')
    addr_comp = comps.get('address')
    if addr_comp and addr_comp['addrnum_type'] == 'Range':
        return []

    tags = []
    for key, path in parser_tags_items:
        value = comps
        for item in path:
            value = value.get(item)
        if value is None:
            continue
        val_str = str(value).strip()
        if val_str and val_str != 'None':
            tags.append((street_address, key, val_str))
    return tags


def _parse_source_chunk(
    chunk: list[str],
) -> list[tuple[str, FastAddress | str, list[tuple[str, str, str]]]]:
    """Worker entrypoint: parse source addresses and extract parser tags."""
    parser = _WORKER_PARSER
    parser_tags_items = _WORKER_PARSER_TAGS
    results = []
    for raw in chunk:
        try:
            parsed = parser.parse(raw)
        except Exception:
            results.append((raw, 'Could not parse', []))
            continue
        tags = extract_parser_tags(parsed, parser_tags_items)
        addr_or_err = build_fast_address(parsed, distinguish_none_type=True)
        results.append((raw, addr_or_err, tags))
    return results


def _parse_address_only_chunk(chunk: list[str]) -> list[tuple[str, FastAddress | str]]:
    """Worker entrypoint: parse addresses without extracting parser tags."""
    parser = _WORKER_PARSER
    results = []
    for raw in chunk:
        try:
            parsed = parser.parse(raw)
        except Exception:
            results.append((raw, 'Could not parse'))
            continue
        results.append((raw, build_fast_address(parsed, distinguish_none_type=False)))
    return results


def _parse_single_address(parser, raw: str) -> FastAddress | str:
    try:
        parsed = parser.parse(raw)
    except Exception:
        return 'Could not parse'
    return build_fast_address(parsed, distinguish_none_type=False)


def _get_parse_workers() -> int:
    env_val = os.environ.get('AIS_PARSE_WORKERS')
    if env_val is not None:
        return max(1, int(env_val))
    return min(os.cpu_count() or 1, 8)


def _chunk_list(items: list[str], num_chunks: int) -> list[list[str]]:
    n = len(items)
    if n == 0:
        return []
    num_chunks = max(1, min(num_chunks, n))
    size, rem = divmod(n, num_chunks)
    chunks = []
    start = 0
    for i in range(num_chunks):
        end = start + size + (1 if i < rem else 0)
        chunks.append(items[start:end])
        start = end
    return chunks


def _batch_parse_source_addresses(
    unique_addrs: list[str],
    executor: ProcessPoolExecutor | None,
    num_workers: int,
    parsed_cache: dict[str, FastAddress | str],
    parser_tag_seen: set[tuple[str, str, str]],
    parser_address_tags: list[dict],
) -> None:
    if not unique_addrs:
        return
    if executor is not None and len(unique_addrs) >= _PARALLEL_PARSE_THRESHOLD:
        chunks = _chunk_list(unique_addrs, num_workers * 4)
        chunk_results = executor.map(_parse_source_chunk, chunks)
    else:
        chunk_results = (_parse_source_chunk(unique_addrs),)

    for batch in chunk_results:
        for raw, addr_or_err, tags in batch:
            parsed_cache[raw] = addr_or_err
            for tag_triple in tags:
                if tag_triple not in parser_tag_seen:
                    parser_tag_seen.add(tag_triple)
                    parser_address_tags.append({
                        'street_address': tag_triple[0],
                        'key': tag_triple[1],
                        'value': tag_triple[2],
                    })


def _batch_parse_address_only(
    unique_addrs: list[str],
    executor: ProcessPoolExecutor | None,
    num_workers: int,
    target_cache: dict[str, FastAddress | str],
) -> None:
    if not unique_addrs:
        return
    if executor is not None and len(unique_addrs) >= _PARALLEL_PARSE_THRESHOLD:
        chunks = _chunk_list(unique_addrs, num_workers * 4)
        chunk_results = executor.map(_parse_address_only_chunk, chunks)
    else:
        chunk_results = (_parse_address_only_chunk(unique_addrs),)

    for batch in chunk_results:
        for raw, addr_or_err in batch:
            target_cache[raw] = addr_or_err


def main():
    global _WORKER_PARSER, _WORKER_PARSER_TAGS

    print('Starting...')
    start = datetime.now()

    street_warning_map.clear()
    street_error_map.clear()

    config = app.config
    parser_tags = config['ADDRESSES']['parser_tags']
    sources = config['ADDRESSES']['sources']
    parcel_layers = config['BASE_DATA_SOURCES']['parcels']

    # Initialize Passyunk and fork worker pool BEFORE opening DB sockets so
    # workers share Passyunk's lookup tables copy-on-write with zero inherited FDs.
    Parser = config['PARSER']
    parser = Parser()
    _WORKER_PARSER = parser
    _WORKER_PARSER_TAGS = tuple(
        (tag_field, tuple(path)) for tag_field, path in parser_tags.items()
    )

    num_workers = _get_parse_workers()
    use_fork_pool = (
        num_workers > 1 and 'fork' in multiprocessing.get_all_start_methods()
    )
    executor = (
        ProcessPoolExecutor(
            max_workers=num_workers,
            mp_context=multiprocessing.get_context('fork'),
        )
        if use_fork_pool
        else None
    )
    if executor is not None:
        print(f'Using {num_workers} forked Passyunk parser workers...')

    db = connect(config['DATABASES']['engine'])
    source_dbs = {'engine': db}
    try:
        _run_load_addresses(
            db=db,
            source_dbs=source_dbs,
            config=config,
            sources=sources,
            parcel_layers=parcel_layers,
            parser=parser,
            executor=executor,
            num_workers=num_workers,
        )
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
        for name, conn in source_dbs.items():
            if name != 'engine':
                conn.close()
        db.close()

    print('Finished in {} seconds'.format(datetime.now() - start))


def _run_load_addresses(
    *,
    db,
    source_dbs,
    config,
    sources,
    parcel_layers,
    parser,
    executor,
    num_workers,
):
    address_table = db['address']
    address_tag_table = db['address_tag']
    source_address_table = db['source_address']
    address_link_table = db['address_link']
    street_segment_table = db['street_segment']
    address_street_table = db['address_street']
    address_parcel_table = db['address_parcel']
    address_property_table = db['address_property']
    address_error_table = db['address_error']
    true_range_view_name = 'true_range'

    true_range_select_stmt = '''
        select
             coalesce(r.seg_id, l.seg_id) as seg_id,
             r.low as true_right_from,
             r.high as true_right_to,
             l.low as true_left_from,
             l.high as true_left_to
        from (select
                  asr.seg_id,
                  min(a.address_low) as low,
                  greatest(max(a.address_low), max(a.address_high)) as high
             from address a join address_street asr on a.street_address = asr.street_address
             group by asr.seg_id, asr.seg_side
             having asr.seg_id is not null and asr.seg_side = 'R') r
        full outer join
             (select
                  asl.seg_id,
                  min(a.address_low) as low,
                  greatest(max(a.address_low), max(a.address_high)) as high
             from address a join address_street asl on a.street_address = asl.street_address
             group by asl.seg_id, asl.seg_side
             having asl.seg_id is not null and asl.seg_side = 'L') l
        on r.seg_id = l.seg_id
        order by r.seg_id
    '''

    WRITE_OUT = True
    DEV = False  # This will target a single address
    DEV_ADDRESS = "1231 N BROAD ST FL 3"
    DEV_ADDRESS_COMPS = {}
    DEV_STREET_NAME = 'N BROAD ST'

    # Logging stuff.
    address_errors = []
    source_map = {}  # source_address => [source_names]
    source_address_map = {}  # street_address => set[source_address]

    """MAIN"""

    addresses: list[FastAddress] = []
    street_addresses_seen: set[str] = set()
    address_tags = []
    parser_address_tags = []
    parser_tag_seen: set[tuple[str, str, str]] = set()
    source_addresses = []
    parsed_cache: dict[str, FastAddress | str] = {}
    base_reparse_cache: dict[str, FastAddress | str] = {}

    if WRITE_OUT:
        print('Dropping indexes...')
        for table in (address_table, address_tag_table, source_address_table, address_street_table):
            table.drop_index('street_address')
        address_link_table.drop_index('address_1')
        address_link_table.drop_index('address_2')

        print('Deleting existing addresses...')
        address_table.delete()
        print('Deleting existing address tags...')
        address_tag_table.delete()
        print('Deleting existing source addresses...')
        source_address_table.delete()
        print('Deleting existing address links...')
        address_link_table.delete()
        print('Deleting address errors...')
        address_error_table.delete()

    # Loop over address sources
    for source in sources:
        source_name = source['name']

        # Determine address field mapping: single or comps
        address_fields = source['address_fields']
        aliases = {value: key for key, value in address_fields.items()}
        if len(address_fields) == 1:
            if 'street_address' in address_fields:
                source_type = 'single_field'
            else:
                raise ValueError('Unknown address field mapping')
            preprocessor = source.get('preprocessor')
        else:
            source_type = 'comps'
            for field_name in ['address_low', 'street_name']:
                if field_name not in address_fields and not all(
                    x in address_fields for x in ['base_address', 'unit_num']
                ):
                    raise ValueError(f'Missing required address field: {field_name}')
            if 'preprocessor' not in source:
                raise ValueError(
                    f'No preprocessor specified for address source `{source_name}`'
                )
            preprocessor = source['preprocessor']

        source_fields = list(address_fields.values())
        tag_fields_spec = []
        for tag_field in source.get('tag_fields', []):
            tag_source_fields = tag_field['source_fields']
            tag_preprocessor = tag_field.get('preprocessor')
            if len(tag_source_fields) > 1 and tag_preprocessor is None:
                raise ValueError('Multiple tag source fields require a preprocessor.')
            source_fields += tag_source_fields
            tag_fields_spec.append(
                (tag_field['key'], tag_preprocessor, tag_source_fields[0])
            )
        source_fields = list(set(source_fields))

        source_db_name = source['db']
        source_db = source_dbs.get(source_db_name)
        if source_db is None:
            source_db = connect(config['DATABASES'][source_db_name])
            source_dbs[source_db_name] = source_db
        source_table = source_db[source['table']]
        print(f'Reading from {source_name}...')

        where = source.get('where')
        if DEV:
            if source_type == 'single_field':
                dev_where = f"{address_fields['street_address']} = '{DEV_ADDRESS}'"
            else:
                clauses = [
                    f"{address_fields[key]} = '{value}'"
                    for key, value in DEV_ADDRESS_COMPS.items()
                ]
                dev_where = ' AND '.join(clauses)
            where = f'{where} AND {dev_where}' if where else dev_where

        source_rows = source_table.read(
            fields=source_fields,
            aliases=aliases,
            where=where,
            return_geom=False,
        )

        if not DEV and (not source_rows or len(source_rows) < 2):
            raise Exception(
                f'Exiting because source table {source_table} is empty.'
            )

        # Phase 1: Extract source_address strings and parallel-parse uncached uniques
        if preprocessor:
            row_source_addresses = [preprocessor(row) for row in source_rows]
        else:
            row_source_addresses = [row['street_address'] for row in source_rows]

        uncached_unique = list(
            dict.fromkeys(
                sa
                for sa in row_source_addresses
                if sa is not None and sa not in parsed_cache
            )
        )
        if uncached_unique:
            print(f'Parsing {len(uncached_unique)} uncached unique addresses for {source_name}...')
            _batch_parse_source_addresses(
                uncached_unique,
                executor,
                num_workers,
                parsed_cache,
                parser_tag_seen,
                parser_address_tags,
            )

        # Pre-parse any uncached base_address strings needed for non-base rows
        uncached_bases = list(
            dict.fromkeys(
                addr.base_address
                for sa in uncached_unique
                if isinstance((addr := parsed_cache.get(sa)), FastAddress)
                and addr.address_low != 0
                and not addr.is_base
                and addr.base_address not in street_addresses_seen
                and addr.base_address not in base_reparse_cache
                and addr.base_address not in parsed_cache
            )
        )
        if uncached_bases:
            _batch_parse_address_only(
                uncached_bases, executor, num_workers, base_reparse_cache
            )

        # Phase 2: Build addresses, tags, source_addresses, and errors
        source_tag_seen: set[tuple[str, str, str]] = set()
        for i, (source_row, source_address) in enumerate(
            zip(source_rows, row_source_addresses)
        ):
            if i % 100000 == 0:
                print(i)

            if source_address is None:
                continue

            source_map.setdefault(source_address, []).append(source_name)
            street_address = None

            try:
                address = parsed_cache[source_address]
                if isinstance(address, str):
                    raise ValueError(address)

                if DEV:
                    print(address.as_dict())

                street_address = address.street_address
                source_address_map.setdefault(street_address, set()).add(source_address)

                if address.address_low == 0:
                    raise ValueError('Low number is zero')

                if street_address not in street_addresses_seen:
                    addresses.append(address)
                    street_addresses_seen.add(street_address)

                source_addresses.append({
                    'source_name': source_name,
                    'source_address': source_address,
                    'street_address': street_address,
                })

                # Make address tags
                for key, tag_preprocessor, first_field in tag_fields_spec:
                    if tag_preprocessor:
                        value = tag_preprocessor(source_row)
                    else:
                        value = source_row[first_field]

                    if value is None:
                        continue
                    if isinstance(value, str):
                        if not value.strip():
                            continue
                        value = value.upper()
                        val_key = value
                    else:
                        val_key = str(value)
                        if not val_key.strip():
                            continue

                    tag_triple = (street_address, key, val_key)
                    if tag_triple not in source_tag_seen:
                        source_tag_seen.add(tag_triple)
                        address_tags.append({
                            'street_address': street_address,
                            'key': key,
                            'value': value,
                        })

                # If it's a unit or low num suffix, make sure we have the base address
                if not address.is_base:
                    base_address = address.base_address
                    if base_address not in street_addresses_seen:
                        base_address_obj = base_reparse_cache.get(base_address)
                        if base_address_obj is None:
                            cached = parsed_cache.get(base_address)
                            if isinstance(cached, FastAddress):
                                base_address_obj = cached
                            else:
                                base_address_obj = _parse_single_address(
                                    parser, base_address
                                )
                            base_reparse_cache[base_address] = base_address_obj

                        if isinstance(base_address_obj, str):
                            raise ValueError(base_address_obj)

                        if base_address != base_address_obj.street_address:
                            raise ValueError('Base address is not reparsable')

                        addresses.append(base_address_obj)
                        street_addresses_seen.add(base_address)
                        source_addresses.append({
                            'source_name': 'AIS',
                            'source_address': base_address,
                            'street_address': base_address,
                        })
                        source_address_map.setdefault(base_address, set()).add(
                            source_address
                        )

            except ValueError as e:
                address_errors.append({
                    'source_name': source_name,
                    'source_address': source_address,
                    'street_address': street_address or '',
                    'level': 'error',
                    'reason': str(e),
                    'notes': '',
                })

        del source_rows
        del row_source_addresses
        source_tag_seen.clear()

        if WRITE_OUT:
            print(f'Writing {len(address_tags)} address tags...')
            address_tag_table.write(address_tags, chunk_size=150000)
            address_tags = []

            print(f'Writing {len(source_addresses)} source addresses...')
            source_address_table.write(source_addresses, chunk_size=150000)
            source_addresses = []

    if WRITE_OUT:
        print(f'Writing {len(addresses)} addresses...')
        insert_rows = [x.as_dict() for x in addresses]
        address_table.write(insert_rows, chunk_size=150000)
        del insert_rows

    print(f'Writing {len(parser_address_tags)} parser_address_tags...')
    if WRITE_OUT:
        address_tag_table.write(parser_address_tags, chunk_size=150000)
    del parser_address_tags
    parser_tag_seen.clear()

    # Spatial parcel id tags from address points (single scan of address_tag)
    print('Ensuring spatial indexes and planner stats on parcels and address points...')
    db.execute("""
        CREATE INDEX IF NOT EXISTS dor_parcel_geom_gix ON dor_parcel USING GIST (geom);
        CREATE INDEX IF NOT EXISTS pwd_parcel_geom_gix ON pwd_parcel USING GIST (geom);
        ANALYZE dor_parcel;
        ANALYZE pwd_parcel;
        ANALYZE ng911_address_point;
    """)
    db.save()

    print('Computing existing parcel tag coverage for ng911 address points...')
    db.execute("""
        CREATE TEMP TABLE tmp_ng911_tag_status ON COMMIT DROP AS
        SELECT
            t.street_address,
            COALESCE(bool_or(t.key = 'dor_parcel_id'), false) AS has_dor,
            COALESCE(bool_or(t.key = 'pwd_parcel_id'), false) AS has_pwd
        FROM address_tag t
        WHERE t.street_address IN (SELECT street_address FROM ng911_address_point)
        GROUP BY t.street_address
    """)
    db.execute('ANALYZE tmp_ng911_tag_status')

    print('Adding dor_parcel_id tags for address points via spatial join...')
    db.execute("""
        INSERT INTO address_tag (street_address, key, value)
        SELECT ng911.street_address, 'dor_parcel_id', dor.parcel_id
        FROM ng911_address_point ng911
        JOIN tmp_ng911_tag_status s
          ON s.street_address = ng911.street_address AND NOT s.has_dor
        JOIN dor_parcel dor
          ON ST_DWithin(dor.geom, ng911.geom, 2)
    """)

    print('Adding pwd_parcel_id tags for address points via spatial join...')
    db.execute("""
        INSERT INTO address_tag (street_address, key, value)
        SELECT ng911.street_address, 'pwd_parcel_id', pwd.parcel_id
        FROM ng911_address_point ng911
        JOIN tmp_ng911_tag_status s
          ON s.street_address = ng911.street_address AND NOT s.has_pwd
        JOIN pwd_parcel pwd
          ON ST_DWithin(pwd.geom, ng911.geom, 2)
    """)
    db.save()

    ###############################################################################
    # ADDRESS LINKS
    ###############################################################################
    print('** ADDRESS LINKS **')
    print('Indexing addresses...')
    generic_unit_types = {'#', 'APT', 'UNIT'}
    apt_unit_types = {'APT', 'UNIT'}

    street_range_by_suffix = {}  # (street_full, parity, address_low_suffix) => [range addresses]
    street_range_by_parity = {}  # (street_full, parity) => [range addresses]
    generic_unit_map = {}  # (base_address, unit_num) => [generic unit addresses]

    for i, address in enumerate(addresses):
        if i % 100000 == 0:
            print(i)

        if address.address_high is not None and address.unit_type is None:
            parity = address.parity
            street_full = address.street_full
            street_range_by_suffix.setdefault(
                (street_full, parity, address.address_low_suffix), []
            ).append(address)
            street_range_by_parity.setdefault((street_full, parity), []).append(address)

        if address.unit_type in generic_unit_types:
            generic_unit_map.setdefault(
                (address.base_address, address.unit_num), []
            ).append(address)

    # Pre-parse all unique candidate range child addresses in parallel
    uncached_children = []
    seen_child_candidates: set[str] = set()
    for address in addresses:
        if not address.address_high:
            continue
        address_suffix = address.address_low_suffix
        street_full = address.street_full
        for x in range(address.address_low, address.address_high + 1, 2):
            child_low = f'{x}{address_suffix}' if address_suffix else str(x)
            child_address = f'{child_low} {street_full}' if street_full else child_low
            if (
                child_address not in street_addresses_seen
                and child_address not in seen_child_candidates
            ):
                seen_child_candidates.add(child_address)
                if (
                    child_address not in base_reparse_cache
                    and not isinstance(parsed_cache.get(child_address), FastAddress)
                ):
                    uncached_children.append(child_address)
    del seen_child_candidates

    if uncached_children:
        print(f'Parsing {len(uncached_children)} candidate range child addresses...')
        _batch_parse_address_only(
            uncached_children, executor, num_workers, base_reparse_cache
        )
    del uncached_children

    print('Making address links...')
    links = []
    seen_links: set[tuple[str, str, str]] = set()
    new_addresses: list[FastAddress] = []

    def add_link(address_1: str, relationship: str, address_2: str) -> None:
        key = (address_1, relationship, address_2)
        if key not in seen_links:
            seen_links.add(key)
            links.append({
                'address_1': address_1,
                'relationship': relationship,
                'address_2': address_2,
            })

    for i, address in enumerate(addresses):
        if i % 100000 == 0:
            print(i)

        street_address = address.street_address
        unit_type = address.unit_type

        if unit_type is not None:
            base_address = address.base_address
            add_link(street_address, 'has base', base_address)

            if address.floor is not None and unit_type != 'FL':
                add_link(street_address, 'on floor', f'{base_address} FL {address.floor}')

            if unit_type in generic_unit_types:
                for base_match in generic_unit_map[(base_address, address.unit_num)]:
                    if unit_type != base_match.unit_type:
                        add_link(street_address, 'matches unit', base_match.street_address)
                        add_link(base_match.street_address, 'matches unit', street_address)

                if unit_type in apt_unit_types:
                    generic_unit = address.generic_unit
                    if generic_unit in street_addresses_seen:
                        add_link(street_address, 'has generic unit', generic_unit)

        elif address.address_high is None:
            address_low = address.address_low
            ranges_on_street = street_range_by_suffix.get(
                (address.street_full, address.parity, address.address_low_suffix)
            )
            if ranges_on_street:
                for range_on_street in ranges_on_street:
                    if range_on_street.address_low <= address_low <= range_on_street.address_high:
                        add_link(street_address, 'in range', range_on_street.street_address)
                        break

        # Create links (and address objects) for all possible addresses in range
        if address.address_high:
            address_low = address.address_low
            address_high = address.address_high
            address_suffix = address.address_low_suffix
            street_full = address.street_full
            unit_num = address.unit_num
            base_address = address.base_address
            base_address_no_suffix = address.base_address_no_suffix
            parity = address.parity

            for x in range(address_low, address_high + 1, 2):
                child_low = f'{x}{address_suffix}' if address_suffix else str(x)
                child_address = f'{child_low} {street_full}' if street_full else child_low
                if child_address in street_addresses_seen:
                    continue

                child_obj = base_reparse_cache.get(child_address)
                if child_obj is None:
                    cached = parsed_cache.get(child_address)
                    if isinstance(cached, FastAddress):
                        child_obj = cached
                    else:
                        child_obj = _parse_single_address(parser, child_address)
                        base_reparse_cache[child_address] = child_obj

                if isinstance(child_obj, str):
                    continue
                child_street_address = child_obj.street_address
                if child_street_address not in street_addresses_seen:
                    if child_obj.address_low == 0:
                        continue
                    new_addresses.append(child_obj)
                    source_addresses.append({
                        'source_name': 'AIS',
                        'source_address': child_street_address,
                        'street_address': child_street_address,
                    })
                    street_addresses_seen.add(child_street_address)
                    add_link(child_street_address, 'in range', base_address)

            # Overlap link (street_range_by_parity only holds unit_type is None)
            if unit_type is None:
                ranges_on_street = street_range_by_parity.get((street_full, parity))
                if ranges_on_street:
                    for range_on_street in ranges_on_street:
                        if (
                            street_address != range_on_street.street_address
                            and base_address != range_on_street.base_address
                            and base_address_no_suffix != range_on_street.base_address_no_suffix
                            and unit_num == range_on_street.unit_num
                            and (
                                range_on_street.address_low <= address_low <= range_on_street.address_high
                                or range_on_street.address_low <= address_high <= range_on_street.address_high
                            )
                        ):
                            add_link(street_address, 'overlaps', range_on_street.street_address)
                            add_link(range_on_street.street_address, 'overlaps', street_address)

    if WRITE_OUT:
        print('Writing address links...')
        address_link_table.write(links, chunk_size=150000)
        print(f'Created {len(links)} address links')

    del links
    seen_links.clear()
    del street_range_by_suffix
    del street_range_by_parity
    del generic_unit_map

    if WRITE_OUT:
        print(f'Writing {len(new_addresses)} new addresses... ')
        insert_rows = [x.as_dict() for x in new_addresses]
        address_table.write(insert_rows, chunk_size=150000)
        del insert_rows

        print(f'Writing {len(source_addresses)} base and in-range AIS source addresses...')
        source_address_table.write(source_addresses, chunk_size=150000)

    source_addresses = []
    del street_addresses_seen

    ###############################################################################
    # ADDRESS-STREETS
    ###############################################################################

    print('** ADDRESS-STREETS **')

    class ContinueIteration(Exception):
        pass

    def had_street_warning(street_address, reason, notes=None):
        address_warnings = street_warning_map.setdefault(street_address, [])
        address_warnings.append({
            'reason': reason,
            'notes': notes or '',
        })

    def had_street_error(street_address, reason, notes=None):
        street_error_map[street_address] = {'reason': reason, 'notes': notes}
        had_street_warning(street_address, reason, notes=notes)
        raise ContinueIteration

    if WRITE_OUT:
        print('Deleting existing address-streets...')
        address_street_table.delete()

    print('Reading street segments...')
    seg_fields = [
        'seg_id',
        'street_full',
        'left_from',
        'left_to',
        'right_from',
        'right_to',
    ]
    seg_map = {}  # street_full => [(seg_id, lf, lt, rf, rt, l_par, r_par), ...]
    seg_rows = street_segment_table.read(
        fields=seg_fields,
        sort=['STREET_FULL', 'LEFT_FROM', 'RIGHT_FROM'],
        return_geom=False,
    )
    for seg_row in seg_rows:
        lf = seg_row['left_from']
        lt = seg_row['left_to']
        rf = seg_row['right_from']
        rt = seg_row['right_to']
        seg_map.setdefault(seg_row['street_full'], []).append((
            seg_row['seg_id'],
            lf,
            lt,
            rf,
            rt,
            parity_for_range(lf, lt),
            parity_for_range(rf, rt),
        ))
    del seg_rows

    address_streets = []
    base_street_match_map = {}  # base_address => (seg_id, seg_side)

    print('Making address-streets...')
    addresses = addresses + new_addresses
    del new_addresses

    for address in addresses:
        try:
            street_address = address.street_address
            base_address = address.base_address

            if base_address in street_error_map:
                error = street_error_map[base_address]
                had_street_error(street_address, error['reason'], notes=error['notes'])

            match = base_street_match_map.get(base_address)
            if match is not None:
                seg_id, seg_side = match
                for warning in street_warning_map.get(base_address, ()):
                    had_street_warning(
                        street_address,
                        warning['reason'],
                        notes=warning.get('notes'),
                    )
            else:
                deferred_warnings = []
                address_low = address.address_low
                address_high = address.address_high
                street_full = address.street_full
                address_parity = address.parity

                matching_segs = seg_map.get(street_full)
                if matching_segs is None:
                    had_street_error(street_address, 'Not a valid street')

                matching_seg_id = None
                matching_side = None

                for seg_id_cand, lf, lt, rf, rt, l_par, r_par in matching_segs:
                    left_ok = l_par == address_parity or l_par == 'B'
                    right_ok = r_par == address_parity or r_par == 'B'

                    if left_ok and not right_ok:
                        check_from, check_to, cand_side = lf, lt, 'L'
                    elif right_ok and not left_ok:
                        check_from, check_to, cand_side = rf, rt, 'R'
                    elif left_ok and right_ok:
                        if abs(address_low - lf) < abs(address_low - rf):
                            check_from, check_to, cand_side = lf, lt, 'L'
                        else:
                            check_from, check_to, cand_side = rf, rt, 'R'
                    else:
                        continue

                    matching_side = cand_side

                    if address_high is None:
                        if check_from <= address_low <= check_to:
                            matching_seg_id = seg_id_cand
                            break
                    else:
                        if check_from <= address_low <= check_to:
                            if matching_seg_id is not None:
                                seg_ids = sorted((matching_seg_id, seg_id_cand))
                                notes = ', '.join(str(x) for x in seg_ids)
                                had_street_error(
                                    street_address,
                                    'Range address matches multiple street segments',
                                    notes=notes,
                                )
                            matching_seg_id = seg_id_cand
                            if check_to < address_high:
                                deferred_warnings.append((
                                    street_address,
                                    'High address out of range',
                                    f'Seg {matching_seg_id}: {check_from} to {check_to}',
                                ))
                        elif check_from <= address_high <= check_to:
                            matching_seg_id = seg_id_cand
                            deferred_warnings.append((
                                street_address,
                                'Low address out of range',
                                f'Seg {matching_seg_id}: {check_from} to {check_to}',
                            ))

                if matching_seg_id is not None:
                    match = (matching_seg_id, matching_side)
                    base_street_match_map[base_address] = match

                for w_addr, w_reason, w_notes in deferred_warnings:
                    had_street_warning(w_addr, w_reason, notes=w_notes)

                if match is None:
                    had_street_error(street_address, 'Out of street range')
                seg_id, seg_side = match

            address_streets.append({
                'street_address': street_address,
                'seg_id': seg_id,
                'seg_side': seg_side,
            })

        except ContinueIteration:
            pass

    if WRITE_OUT:
        print('Writing address-streets...')
        address_street_table.write(address_streets, chunk_size=150000)
    del address_streets
    del seg_map
    del base_street_match_map

    # Handle errors
    for street_address, warnings in street_warning_map.items():
        _source_addresses = source_address_map.get(street_address)
        if not _source_addresses:
            continue
        for warning_dict in warnings:
            reason = warning_dict['reason']
            notes = warning_dict['notes']
            for src_addr in _source_addresses:
                for src_name in source_map[src_addr]:
                    address_errors.append({
                        'source_name': src_name,
                        'source_address': src_addr,
                        'street_address': street_address,
                        'level': 'warning',
                        'reason': reason,
                        'notes': notes,
                    })

    del source_map
    del source_address_map

    ################################################################################
    # ADDRESS-PARCELS
    ################################################################################

    print('** ADDRESS-PARCELS **')

    match_counts = {
        'base': 0,
        'base_no_suffix': 0,
        'generic_unit': 0,
        'address_in_parcel_range': 0,
        'parcel_in_address_range': 0,
    }

    address_parcels = []

    if WRITE_OUT:
        print('Dropping index on address-parcels...')
        address_parcel_table.drop_index('street_address')
        print('Deleting existing address-parcels...')
        address_parcel_table.delete()

    for parcel_layer in parcel_layers:
        source_table_name = parcel_layer + '_parcel'
        source_table = db[source_table_name]
        print(f'Reading from {parcel_layer}...')

        if DEV:
            where = f"street_name = '{DEV_STREET_NAME}'"
            parcel_rows = source_table.read(
                fields=['street_address', 'id'], where=where, return_geom=False
            )
        else:
            parcel_rows = source_table.read(
                fields=['street_address', 'id'], return_geom=False
            )

        print('Building indexes...')
        parcel_map = {}  # street_address => [row_ids]
        # Pre-indexed range lookup maps avoid linear scans + repeated parity calls:
        # (street_full, hundred_block, unit_full, address_low_suffix, parity) => [...]
        range_block_map = {}  # parcels with address_high is not None: [(row_id, low, high)]
        all_block_map = {}  # all parcels keyed by parity_for_num(low): [(row_id, low)]

        for parcel_row in parcel_rows:
            street_address = parcel_row['street_address']
            row_id = parcel_row['id']

            parcel_address = parsed_cache.get(street_address)
            if parcel_address is None:
                parcel_address = base_reparse_cache.get(street_address)
            if parcel_address is None:
                parcel_address = _parse_single_address(parser, street_address)
                base_reparse_cache[street_address] = parcel_address
            if isinstance(parcel_address, str):
                continue

            parcel_map.setdefault(street_address, []).append(row_id)

            street_full = parcel_address.street_full
            hundred_block = parcel_address.hundred_block
            unit_full = parcel_address.unit_full
            low_suffix = parcel_address.address_low_suffix
            p_low = parcel_address.address_low
            p_high = parcel_address.address_high

            low_key = (
                street_full,
                hundred_block,
                unit_full,
                low_suffix,
                parity_for_num(p_low),
            )
            all_block_map.setdefault(low_key, []).append((row_id, p_low))

            if p_high is not None:
                range_key = (
                    street_full,
                    hundred_block,
                    unit_full,
                    low_suffix,
                    parity_for_range(p_low, p_high),
                )
                range_block_map.setdefault(range_key, []).append(
                    (row_id, p_low, p_high)
                )

        del parcel_rows

        print('Relating addresses to parcels...')
        for address in addresses:
            street_address = address.street_address

            # EXACT
            exact_ids = parcel_map.get(street_address)
            if exact_ids is not None:
                for row_id in exact_ids:
                    address_parcels.append({
                        'street_address': street_address,
                        'parcel_source': parcel_layer,
                        'parcel_row_id': row_id,
                        'match_type': 'exact',
                    })
                continue

            # BASE, BASE NO SUFFIX, GENERIC UNIT (first matching row_id)
            matched = False
            for variant, match_type in (
                (address.base_address, 'base'),
                (address.base_address_no_suffix, 'base_no_suffix'),
                (address.generic_unit, 'generic_unit'),
            ):
                row_ids = parcel_map.get(variant)
                if row_ids:
                    address_parcels.append({
                        'street_address': street_address,
                        'parcel_source': parcel_layer,
                        'parcel_row_id': row_ids[0],
                        'match_type': match_type,
                    })
                    match_counts[match_type] += 1
                    matched = True
                    break

            if matched:
                continue

            # RANGES
            address_low = address.address_low
            address_high = address.address_high
            lookup_key = (
                address.street_full,
                address.hundred_block,
                address.unit_full,
                address.address_low_suffix,
                address.parity,
            )

            if address_high is None:
                # SINGLE ADDRESS => RANGE PARCEL
                candidates = range_block_map.get(lookup_key)
                if candidates:
                    for row_id, parcel_low, parcel_high in candidates:
                        if parcel_low <= address_low <= parcel_high:
                            match_counts['address_in_parcel_range'] += 1
                            address_parcels.append({
                                'street_address': street_address,
                                'parcel_source': parcel_layer,
                                'parcel_row_id': row_id,
                                'match_type': 'address_in_parcel_range',
                            })
            else:
                # RANGE ADDRESS => SINGLE PARCEL(S)
                candidates = all_block_map.get(lookup_key)
                if candidates:
                    for row_id, parcel_low in candidates:
                        if address_low <= parcel_low <= address_high:
                            match_counts['parcel_in_address_range'] += 1
                            address_parcels.append({
                                'street_address': street_address,
                                'parcel_source': parcel_layer,
                                'parcel_row_id': row_id,
                                'match_type': 'parcel_in_address_range',
                            })

        del parcel_map
        del range_block_map
        del all_block_map

    if WRITE_OUT:
        print('Writing address-parcels...')
        address_parcel_table.write(address_parcels, chunk_size=150000)
        print('Indexing address-parcels...')
        address_parcel_table.create_index('street_address')

    for variant_type, count in match_counts.items():
        print(f'{count} matched on {variant_type}')

    del address_parcels

    ################################################################################
    # ADDRESS-PROPERTIES
    ################################################################################

    print('** ADDRESS-PROPERTIES **')

    if WRITE_OUT:
        print('Dropping index on address-properties...')
        address_property_table.drop_index('street_address')
        print('Deleting existing address-properties...')
        address_property_table.delete()

    print('Reading properties from AIS...')
    prop_rows = db['opa_property'].read(
        fields=['street_address', 'account_num', 'address_low', 'address_high', 'unit_num'],
        return_geom=False,
    )
    prop_map = {x['street_address']: x['account_num'] for x in prop_rows}

    print('Indexing range properties...')
    # (street_full, range_parity) => [(low, high, unit_num, account_num), ...]
    range_map = {}
    for row in prop_rows:
        p_high = row['address_high']
        if p_high is None:
            continue
        street_address = row['street_address']
        parsed_addr = parsed_cache.get(street_address)
        if parsed_addr is None:
            parsed_addr = base_reparse_cache.get(street_address)
        if parsed_addr is None:
            parsed_addr = _parse_single_address(parser, street_address)
            base_reparse_cache[street_address] = parsed_addr
        if isinstance(parsed_addr, str):
            print(f'Unrecognized format for range address: {street_address}')
            continue
        p_low = row['address_low']
        r_parity = parity_for_range(p_low, p_high)
        range_map.setdefault((parsed_addr.street_full, r_parity), []).append(
            (p_low, p_high, row['unit_num'], row['account_num'])
        )
    del prop_rows
    del parsed_cache
    del base_reparse_cache

    address_props = []

    print('Relating addresses to properties...')
    for i, address in enumerate(addresses):
        if i % 100000 == 0:
            print(i)

        street_address = address.street_address
        unit_num = address.unit_num
        account_num = None
        match_type = None

        # EXACT
        if street_address in prop_map:
            account_num = prop_map[street_address]
            match_type = 'exact'
        # BASE
        elif unit_num and address.base_address in prop_map:
            account_num = prop_map[address.base_address]
            match_type = 'base'
        # BASE NO SUFFIX
        elif address.base_address_no_suffix in prop_map:
            account_num = prop_map[address.base_address_no_suffix]
            match_type = 'base_no_suffix'
        # GENERIC UNIT
        elif unit_num and address.generic_unit in prop_map:
            account_num = prop_map[address.generic_unit]
            match_type = 'generic_unit'
        # RANGE
        elif address.address_high is None:
            range_props = range_map.get((address.street_full, address.parity))
            if range_props:
                addr_low = address.address_low
                for rp_low, rp_high, rp_unit_num, rp_acct in range_props:
                    if rp_low <= addr_low <= rp_high:
                        if (unit_num or rp_unit_num) and unit_num != rp_unit_num:
                            continue
                        account_num = rp_acct
                        match_type = 'range'
                        break

        if match_type is not None:
            address_props.append({
                'street_address': street_address,
                'opa_account_num': account_num,
                'match_type': match_type,
            })

    if WRITE_OUT:
        address_property_table.write(address_props, chunk_size=150000)
        print('Indexing address-properties...')
        address_property_table.create_index('street_address')
    del address_props
    del prop_map
    del range_map

    ################################################################################
    # TRUE RANGE
    ################################################################################

    print('** TRUE RANGE **')

    if WRITE_OUT:
        print('Creating true range view...')
        db.drop_view(true_range_view_name)
        db.create_view(true_range_view_name, true_range_select_stmt)

    ################################################################################
    # ERRORS
    ################################################################################

    print('** ERRORS **')

    if WRITE_OUT:
        print('Writing errors...')
        address_error_table.write(address_errors, chunk_size=150000)
    del address_errors

    ################################################################################
    # FINISH
    ################################################################################

    print('** FINISHING **')

    if WRITE_OUT:
        print('Creating indexes...')
        for table in (address_table, address_tag_table, source_address_table):
            table.create_index('street_address')
        address_link_table.create_index('address_1')
        address_link_table.create_index('address_2')
        address_street_table.create_index('street_address')
