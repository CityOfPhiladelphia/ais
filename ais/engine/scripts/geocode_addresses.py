"""Geocode addresses against street centerlines, true ranges, parcels, curbs, and NG911.

Performance improvements over the legacy version:
- Uses a single-scan CASE query for parcel centroids (replaces double-scan UNION).
- Uses an in-memory Shapely STRtree spatial index for spatial parcel fallback
  (eliminates hundreds of thousands of per-address PostGIS roundtrip queries).
- Compatible with Shapely 2.x (`MultiLineString.geoms`).
"""

import traceback
from datetime import datetime

from shapely.geometry import LineString, MultiLineString, Point
from shapely.strtree import STRtree
from shapely.wkt import dumps, loads

from ais import app, util
from ais.engine.db import connect


def _extract_xsect_coord(geom):
    """Extract the second coordinate of a LineString or last part of a MultiLineString."""
    if isinstance(geom, LineString):
        coords = geom.coords
        return coords[1] if len(coords) > 1 else None
    if isinstance(geom, MultiLineString) and len(geom.geoms) > 0:
        coords = geom.geoms[-1].coords
        return coords[1] if len(coords) > 1 else None
    return None


def main():
    start = datetime.now()
    print("Starting geocode_addresses...")

    config = app.config
    engine_srid = config["ENGINE_SRID"]
    db = connect(config["DATABASES"]["engine"])

    parcel_layers = config["BASE_DATA_SOURCES"]["parcels"]
    address_table = db["address"]
    address_fields = ["id", "street_address", "address_low", "address_high"]
    seg_table = db["street_segment"]
    seg_fields = ["seg_id", "left_from", "left_to", "right_from", "right_to"]
    geocode_table = db["geocode"]
    parcel_curb_table = db["parcel_curb"]
    curb_table = db["curb"]
    addr_street_table = db["address_street"]
    addr_parcel_table = db["address_parcel"]
    true_range_view = db["true_range"]
    centerline_offset = config["GEOCODE"]["centerline_offset"]
    centerline_end_buffer = config["GEOCODE"]["centerline_end_buffer"]
    geocode_priority_map = config["ADDRESS_SUMMARY"]["geocode_priority"]

    print("Dropping indexes and clearing existing geocodes...")
    geocode_table.drop_index("street_address")
    geocode_table.delete()
    db.execute("DELETE FROM address_parcel WHERE match_type = 'spatial'")
    db.save()

    print("Reading streets from AIS...")
    seg_rows = seg_table.read(fields=seg_fields, geom_field="geom")
    seg_geom_field = seg_table.geom_field
    seg_map = {}
    for seg_row in seg_rows:
        seg_map[seg_row["seg_id"]] = {
            "L": {"low": seg_row["left_from"], "high": seg_row["left_to"]},
            "R": {"low": seg_row["right_from"], "high": seg_row["right_to"]},
            "shape": loads(seg_row[seg_geom_field]),
        }

    print("Reading parcels and building in-memory STRtree spatial indexes...")
    parcel_xy_map = {}      # layer -> int id -> Point
    parcel_wkt_map = {}     # layer -> int id -> WKT str
    parcel_geom_map = {}    # layer -> int id -> Polygon/MultiPolygon
    parcel_trees = {}       # layer -> (STRtree, [parcel_id, ...])

    for parcel_layer_name in parcel_layers:
        source_table = f"{parcel_layer_name}_parcel"
        print(f"  - {parcel_layer_name}")
        parcel_stmt = f"""
            SELECT
                id,
                ST_AsText(geom) AS geom,
                CASE
                    WHEN ST_Intersects(ST_Centroid(geom), geom)
                    THEN ST_AsText(ST_Centroid(geom))
                    ELSE ST_AsText(ST_PointOnSurface(geom))
                END AS centroid
            FROM {source_table}
            WHERE geom IS NOT NULL
        """
        parcel_rows = db.execute(parcel_stmt)
        layer_xy = {}
        layer_wkt = {}
        layer_geom = {}
        tree_ids = []
        tree_geoms = []
        for row in parcel_rows:
            pid = row["id"]
            centroid_wkt = row["centroid"]
            poly = loads(row["geom"])
            layer_xy[pid] = loads(centroid_wkt)
            layer_wkt[pid] = centroid_wkt
            layer_geom[pid] = poly
            tree_ids.append(pid)
            tree_geoms.append(poly)

        parcel_xy_map[parcel_layer_name] = layer_xy
        parcel_wkt_map[parcel_layer_name] = layer_wkt
        parcel_geom_map[parcel_layer_name] = layer_geom
        parcel_trees[parcel_layer_name] = (STRtree(tree_geoms), tree_ids) if tree_geoms else (None, [])

    print("Reading true range...")
    for row in true_range_view.read():
        seg_id = row["seg_id"]
        if seg_id in seg_map:
            seg_map[seg_id]["L"]["true_low"] = row["true_left_from"]
            seg_map[seg_id]["L"]["true_high"] = row["true_left_to"]
            seg_map[seg_id]["R"]["true_low"] = row["true_right_from"]
            seg_map[seg_id]["R"]["true_high"] = row["true_right_to"]

    print("Reading curbs...")
    curb_map = {x["curb_id"]: loads(x["geom"]) for x in curb_table.read(to_srid=engine_srid)}

    print("Reading parcel-curbs...")
    parcel_curb_map = {"dor": {}, "pwd": {}}
    for x in parcel_curb_table.read():
        src = x["parcel_source"]
        if src in parcel_curb_map:
            parcel_curb_map[src][int(x["parcel_row_id"])] = x["curb_id"]

    print("Reading addresses, address-streets, and address-parcels...")
    address_rows = address_table.read(fields=address_fields)
    addr_street_map = {x["street_address"]: (x["seg_id"], x["seg_side"]) for x in addr_street_table.read()}

    addr_parcel_map = {}
    for row in addr_parcel_table.read():
        addr_parcel_map.setdefault(row["street_address"], {}).setdefault(
            row["parcel_source"], []
        ).append(row["parcel_row_id"])

    print("Geocoding addresses...")
    geocode_rows = []
    geocode_count = 0
    address_parcels = []

    gt_centerline = geocode_priority_map["centerline"]
    gt_true_range = geocode_priority_map["true_range"]

    for i, address_row in enumerate(address_rows):
        try:
            if i and i % 100000 == 0:
                print(f"  processed {i} addresses...")

            if len(geocode_rows) >= 150000:
                geocode_table.write(geocode_rows, chunk_size=150000)
                geocode_count += len(geocode_rows)
                geocode_rows = []

            street_address = address_row["street_address"]
            address_low = address_row["address_low"]
            address_high = address_row["address_high"]
            address_num = address_low + (address_high - address_low) / 2 if address_high else address_low

            seg_info = addr_street_map.get(street_address)
            seg_id, seg_side = seg_info if seg_info else (None, None)

            seg_shp = None
            true_xsect_xy = None
            if seg_id:
                seg = seg_map[seg_id]
                seg_shp = seg["shape"]
                side_info = seg[seg_side]

                # CENTERLINE
                low, high = side_info["low"], side_info["high"]
                side_delta = high - low
                distance_ratio = 0.5 if side_delta == 0 else (address_num - low) / side_delta
                seg_xsect_xy = util.interpolate_buffered(seg_shp, distance_ratio, centerline_end_buffer)
                seg_xy = util.offset(seg_shp, seg_xsect_xy, centerline_offset, seg_side)
                geocode_rows.append({
                    "street_address": street_address,
                    "geocode_type": gt_centerline,
                    "geom": dumps(seg_xy),
                })

                # TRUE RANGE
                true_low, true_high = side_info["true_low"], side_info["true_high"]
                true_side_delta = true_high - true_low
                true_distance_ratio = 0.5 if true_side_delta == 0 else (address_num - true_low) / true_side_delta
                true_xsect_xy = util.interpolate_buffered(seg_shp, true_distance_ratio, centerline_end_buffer)
                true_seg_xy = util.offset(seg_shp, true_xsect_xy, centerline_offset, seg_side)
                geocode_rows.append({
                    "street_address": street_address,
                    "geocode_type": gt_true_range,
                    "geom": dumps(true_seg_xy),
                })

            # PARCELS
            addr_parcels_for_addr = addr_parcel_map.get(street_address)
            for parcel_layer_name in parcel_layers:
                source_table = f"{parcel_layer_name}_parcel"
                parcel_ids = addr_parcels_for_addr.get(parcel_layer_name) if addr_parcels_for_addr else None
                parcel_id = None
                parcel_xy = None

                if parcel_ids:
                    if len(parcel_ids) == 1:
                        parcel_id = parcel_ids[0]
                        parcel_xy = parcel_xy_map[parcel_layer_name][parcel_id]
                        geocode_rows.append({
                            "street_address": street_address,
                            "geocode_type": geocode_priority_map[source_table],
                            "geom": parcel_wkt_map[parcel_layer_name][parcel_id],
                        })
                elif seg_id and true_xsect_xy is not None:
                    # SPATIAL MATCH via in-memory STRtree (zero DB roundtrips!)
                    tree, tree_ids = parcel_trees[parcel_layer_name]
                    if tree is not None:
                        for test_offset in (10, 20, 30, 40):
                            test_xy_shp = util.offset(seg_shp, true_xsect_xy, test_offset, seg_side)
                            hits = tree.query(test_xy_shp, predicate="intersects")
                            if len(hits) > 0:
                                parcel_id = tree_ids[int(hits[0])]
                                geocode_rows.append({
                                    "street_address": street_address,
                                    "geocode_type": geocode_priority_map[source_table + "_spatial"],
                                    "geom": parcel_wkt_map[parcel_layer_name][parcel_id],
                                })
                                address_parcels.append({
                                    "street_address": street_address,
                                    "parcel_source": parcel_layer_name,
                                    "parcel_row_id": parcel_id,
                                    "match_type": "spatial",
                                })
                                break

                # CURBSIDE, IN_STREET, & PARCEL FRONT
                if seg_id and parcel_id and parcel_xy is not None and seg_shp is not None:
                    curb_id = parcel_curb_map[parcel_layer_name].get(parcel_id)
                    if curb_id is not None:
                        curb_shp = curb_map[curb_id]
                        proj_dist = seg_shp.project(parcel_xy)
                        proj_xy = seg_shp.interpolate(proj_dist)
                        proj_shp = LineString([parcel_xy, proj_xy])

                        curb_xsect_pt = _extract_xsect_coord(curb_shp.intersection(proj_shp))
                        if curb_xsect_pt:
                            geocode_rows.append({
                                "street_address": street_address,
                                "geocode_type": geocode_priority_map[parcel_layer_name + "_curb"],
                                "geom": dumps(Point(curb_xsect_pt)),
                            })
                            xy_in_street = (
                                (proj_xy.x + curb_xsect_pt[0]) / 2,
                                (proj_xy.y + curb_xsect_pt[1]) / 2,
                            )
                            geocode_rows.append({
                                "street_address": street_address,
                                "geocode_type": geocode_priority_map[parcel_layer_name + "_street"],
                                "geom": dumps(Point(xy_in_street)),
                            })

                        parcel_geom = parcel_geom_map[parcel_layer_name].get(parcel_id)
                        if parcel_geom is not None:
                            front_pt = _extract_xsect_coord(parcel_geom.intersection(proj_shp))
                            if front_pt:
                                geocode_rows.append({
                                    "street_address": street_address,
                                    "geocode_type": geocode_priority_map[parcel_layer_name + "_parcel_front"],
                                    "geom": dumps(Point(front_pt)),
                                })

        except ValueError as e:
            print(e)
        except Exception:
            print(traceback.format_exc())
            raise

    if geocode_rows:
        print("Writing remaining geocodes...")
        geocode_table.write(geocode_rows, chunk_size=150000)
        geocode_count += len(geocode_rows)

    if address_parcels:
        print(f"Writing {len(address_parcels)} spatial address-parcels...")
        addr_parcel_table.write(address_parcels, chunk_size=150000)

    print(f"Wrote {geocode_count} geocode rows")

    print("Inserting NG911 address point geocodes in batch...")
    db.execute(f"""
        INSERT INTO geocode (street_address, geocode_type, geom)
        SELECT street_address, {geocode_priority_map['ng911']} AS geocode_type, geom
        FROM ng911_address_point
    """)
    db.save()

    print("Creating index on geocode(street_address)...")
    geocode_table.create_index("street_address")
    db.close()
    print(f"Finished geocode_addresses in {datetime.now() - start}")
