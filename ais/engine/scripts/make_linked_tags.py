"""Propagate address tags across linked addresses.

Performance optimizations:
- Pushes `address_tag` key filtering and per-(street_address, key) MIN aggregation
  into PostgreSQL (parallel HashAggregate with `COLLATE "C"` matching Python `<`),
  avoiding transferring millions of non-traversable tags over the wire.
- Uses plain tuple cursors instead of RealDictCursor for all bulk reads (eliminates
  ~15M+ Python dict allocations).
- Pre-sorts links by traversal order, pre-filters geocode-conflicting links once, and
  hoists resolved target-tag lookups outside the per-tag-key loop (~15x fewer lookups).
- Uses reverse-adjacency frontier tracking so iterations 2+ only inspect addresses
  whose link targets actually gained new tags on the prior iteration.
- Pass 2 indexes ranged parent children by `(parent_address, 7-tuple component signature)`
  for O(1) lookups using already-parsed `address` columns (zero Passyunk calls).
- Stores new linked tags as compact 5-tuples and streams them directly via chunked
  PostgreSQL `COPY FROM STDIN` while `address_tag(street_address)` index is dropped.
"""

from datetime import datetime
from ais import app
from ais.engine.db import connect, copy_rows_to_table


TRAVERSAL_ORDER = (
    "has generic unit",
    "matches unit",
    "on floor",
    "has base",
    "overlaps",
    "in range",
)
TRAVERSAL_RANK = {rel: idx for idx, rel in enumerate(TRAVERSAL_ORDER)}
_TAG_COLUMNS = ["street_address", "key", "value", "linked_address", "linked_path"]
_COPY_CHUNK_SIZE = 150000


def _has_conflicting_parcel_geocodes(addr_a: str, addr_b: str, geocode_map: dict) -> bool:
    ga = geocode_map.get(addr_a)
    gb = geocode_map.get(addr_b)
    if ga is None or gb is None:
        return False
    pwd_a, dor_a = ga
    pwd_b, dor_b = gb
    return (pwd_b is not None and pwd_b != pwd_a) and (dor_b is not None and dor_b != dor_a)


def _copy_tag_tuples(conn, rows: list[tuple[str, str, str, str, str]]) -> None:
    for start in range(0, len(rows), _COPY_CHUNK_SIZE):
        copy_rows_to_table(
            conn,
            "address_tag",
            _TAG_COLUMNS,
            rows[start : start + _COPY_CHUNK_SIZE],
            truncate=False,
        )


def main():
    start = datetime.now()
    print(f"Starting make_linked_tags at {start}")

    config = app.config
    db = connect(config["DATABASES"]["engine"])
    address_tag_table = db["address_tag"]
    traversable_keys = [
        tf["tag_key"]
        for tf in config["ADDRESS_SUMMARY"]["tag_fields"]
        if tf["traverse_links"] == "true"
    ]
    num_traversable = len(traversable_keys)

    # Give PostgreSQL generous memory for parallel hash aggregates & link sorting
    db.execute("SET work_mem = '256MB'")

    print("Deleting existing linked tags...")
    db.execute("DELETE FROM address_tag WHERE linked_address IS NOT NULL AND linked_address != ''")
    db.save()

    with db.conn.cursor() as cur:
        print("Reading parcel geocodes (types 1, 2)...")
        geocode_map: dict[str, list[str | None]] = {}
        cur.execute(
            "SELECT street_address, geocode_type, geom FROM geocode WHERE geocode_type IN (1, 2)"
        )
        for addr, gtype, geom in cur:
            entry = geocode_map.get(addr)
            if entry is None:
                entry = ["", ""]
                geocode_map[addr] = entry
            if gtype == 1:
                entry[0] = geom
            else:
                entry[1] = geom
        print(f"  loaded {len(geocode_map)} geocoded addresses")

        print("Reading and pre-sorting address links...")
        raw_links: dict[str, list[tuple[int, str, str]]] = {}
        cur.execute(
            """
            SELECT address_1, relationship, address_2
            FROM address_link
            WHERE relationship = ANY(%s)
            ORDER BY address_1, address_2
            """,
            (list(TRAVERSAL_ORDER),),
        )
        for addr_1, rel, addr_2 in cur:
            raw_links.setdefault(addr_1, []).append((TRAVERSAL_RANK[rel], rel, addr_2))

        # Pre-sort by traversal order, filter conflicting parcel geocode pairs,
        # and build reverse adjacency (`addr_2 -> [addr_1, ...]`) for frontier propagation.
        link_map: dict[str, list[tuple[str, str]]] = {}
        reverse_link_map: dict[str, list[str]] = {}
        rejected_link_count = 0
        for addr_1, links in raw_links.items():
            links.sort(key=lambda item: item[0])
            filtered = []
            for _, rel, addr_2 in links:
                if _has_conflicting_parcel_geocodes(addr_1, addr_2, geocode_map):
                    rejected_link_count += 1
                    continue
                filtered.append((rel, addr_2))
                reverse_link_map.setdefault(addr_2, []).append(addr_1)
            if filtered:
                link_map[addr_1] = filtered
        del raw_links
        print(
            f"  indexed links for {len(link_map)} addresses "
            f"({rejected_link_count} conflicting links rejected)"
        )

        print("Reading traversable address tags (aggregated in PostgreSQL)...")
        # tag_map[street_address][key] = (min_value, linked_address, linked_path)
        # All existing linked tags were deleted above, so linked_address/path are ''.
        tag_map: dict[str, dict[str, tuple[str, str, str]]] = {}
        cur.execute(
            """
            SELECT street_address, key, MIN(COALESCE(value, '') COLLATE "C")
            FROM address_tag
            WHERE key = ANY(%s)
            GROUP BY street_address, key
            """,
            (traversable_keys,),
        )
        for addr, key, min_val in cur:
            tag_map.setdefault(addr, {})[key] = (min_val, "", "")
        print(f"  indexed tags for {len(tag_map)} addresses")

    # -------------------------------------------------------------------------
    # Pass 1: Frontier-driven fixed-point propagation along sorted links
    # -------------------------------------------------------------------------
    print("Propagating linked tags...")
    all_linked_tags: list[tuple[str, str, str, str, str]] = []
    frontier = list(link_map.keys())
    iteration = 1

    while frontier:
        new_tags: list[tuple[str, str, str, str, str]] = []
        updated_addrs: set[str] = set()

        for street_address in frontier:
            addr_tags = tag_map.get(street_address)
            if addr_tags is not None and len(addr_tags) == num_traversable:
                continue

            # Resolve target tag dicts once per address instead of once per tag_key
            resolved_links = []
            for rel, link_address in link_map[street_address]:
                link_tags = tag_map.get(link_address)
                if link_tags is not None:
                    resolved_links.append((rel, link_address, link_tags))
            if not resolved_links:
                continue

            for tag_key in traversable_keys:
                if addr_tags is not None and tag_key in addr_tags:
                    continue

                for rel, link_address, link_tags in resolved_links:
                    best = link_tags.get(tag_key)
                    if best is None:
                        continue
                    tag_value, src_linked_addr, src_linked_path = best
                    linked_address = src_linked_addr or link_address
                    linked_path = f"{street_address} {rel} {src_linked_path or link_address}"
                    new_tags.append((
                        street_address,
                        tag_key,
                        tag_value,
                        linked_address,
                        linked_path,
                    ))
                    updated_addrs.add(street_address)
                    break

        print(f"  iteration {iteration}: scanned {len(frontier)} addrs -> {len(new_tags)} new linked tags")
        if not new_tags:
            break

        # Merge newly discovered tags into tag_map before advancing the frontier
        for street_address, key, val, linked_address, linked_path in new_tags:
            addr_tags = tag_map.setdefault(street_address, {})
            existing = addr_tags.get(key)
            if existing is None or val < existing[0]:
                addr_tags[key] = (val, linked_address, linked_path)

        all_linked_tags.extend(new_tags)

        # Only addresses that link TO an address updated in this round can gain new tags next round
        next_frontier_set: set[str] = set()
        for changed_addr in updated_addrs:
            for dependent_addr in reverse_link_map.get(changed_addr, ()):
                next_frontier_set.add(dependent_addr)
        frontier = list(next_frontier_set)
        iteration += 1

    del link_map, reverse_link_map

    # -------------------------------------------------------------------------
    # Pass 2: has base in range unit child (O(1) signature lookup, zero Passyunk)
    # -------------------------------------------------------------------------
    print("Pass 2: Searching for linked tags via 'has base in range unit child'...")

    with db.conn.cursor() as cur:
        addr_sig_map: dict[str, tuple] = {}
        cur.execute("""
            SELECT street_address, address_low, street_predir, street_name,
                   street_suffix, street_postdir, unit_type, unit_num
            FROM address
            WHERE unit_num != ''
            ORDER BY street_address
        """)
        for (
            s_addr,
            addr_low,
            predir,
            st_name,
            st_suffix,
            postdir,
            unit_type,
            unit_num,
        ) in cur:
            addr_sig_map[s_addr] = (
                addr_low or "",
                predir or "",
                st_name or "",
                st_suffix or "",
                postdir or "",
                unit_type or "",
                unit_num or "",
            )

        # Index ranged parent -> (child_sig -> [child_street_address, ...]) for O(1) matching
        range_child_by_sig: dict[tuple[str, tuple], list[str]] = {}
        cur.execute("""
            SELECT al.address_1, al.address_2
            FROM address a
            INNER JOIN address_link al ON al.address_2 = a.street_address
            WHERE a.address_high IS NOT NULL
              AND al.relationship = 'has base'
            ORDER BY al.address_1
        """)
        for child_addr, parent_addr in cur:
            child_sig = addr_sig_map.get(child_addr)
            if child_sig is None:
                continue
            if _has_conflicting_parcel_geocodes(parent_addr, child_addr, geocode_map):
                continue
            range_child_by_sig.setdefault((parent_addr, child_sig), []).append(child_addr)

    pass2_tags: list[tuple[str, str, str, str, str]] = []
    for street_address, sig in addr_sig_map.items():
        addr_tags = tag_map.get(street_address)
        if not addr_tags or len(addr_tags) == num_traversable:
            continue

        # Distinct (linked_address, linked_path) pairs sorted deterministically
        linked_sources = sorted({(la, lp) for _, la, lp in addr_tags.values() if la})
        if not linked_sources:
            continue

        for tag_key in traversable_keys:
            if tag_key in addr_tags:
                continue

            found = False
            for linked_address, linked_path in linked_sources:
                if found:
                    break
                matching_children = range_child_by_sig.get((linked_address, sig))
                if not matching_children:
                    continue
                for l_street_address in matching_children:
                    child_tags = tag_map.get(l_street_address)
                    if not child_tags or tag_key not in child_tags:
                        continue
                    pass2_tags.append((
                        street_address,
                        tag_key,
                        child_tags[tag_key][0],
                        l_street_address,
                        f"{linked_path} unit child {l_street_address}",
                    ))
                    found = True
                    break

    total_new = len(all_linked_tags) + len(pass2_tags)
    if total_new > 0:
        # Drop index during bulk COPY and rebuild once at the end (3x-5x faster)
        print("Dropping address_tag(street_address) index before bulk COPY...")
        address_tag_table.drop_index("street_address")

        if all_linked_tags:
            print(f"Writing {len(all_linked_tags)} linked tags from pass 1...")
            _copy_tag_tuples(db.conn, all_linked_tags)
            del all_linked_tags

        if pass2_tags:
            print(f"Writing {len(pass2_tags)} linked tags from pass 2...")
            _copy_tag_tuples(db.conn, pass2_tags)
            del pass2_tags

        print("Rebuilding address_tag(street_address) index...")
        address_tag_table.create_index("street_address")

    db.close()
    print(f"Finished make_linked_tags in {datetime.now() - start}")
