# API Usage

## Authentication

AIS does not have any authentication on its own, but it is made to sit behind
Philadelphia's [GateKeeper](developer.phila.gov) instance. You must use a GK
API key to access the API. You can sign up for an API key at
https://developer.phila.gov/keys.

Authentication is performed in one of two ways: either with an `Authorization`
header, or with a querystring parameter.  For example, the following would work
as valid requests:

```bash
# Authorization via request header
curl "https://api.phila.gov/ais/v1/addresses/1234%20Market%20St" \
    -H "Authorization: Gatekeeper-Key abcd1234efab5678cdef9012abcd3456"
```

```bash
# Authorization via querystring parameter
curl "https://api.phila.gov/ais/v1/addresses/1234%20Market%20St?gatekeeperKey=abcd1234efab5678cdef9012abcd3456"
```

## Response Structure & Metadata

Addresses for all endpoints except */account* are returned in a paginated
[GeoJSON](http://geojson.org/geojson-spec.html) [FeatureCollection](http://geojson.org/geojson-spec.html#feature-collection-objects).

The root of the `FeatureCollection` contains:
* Pagination information.
  * `page`: The current page of data
  * `page_count`: The total number of pages of data for the current query
  * `page_size`: The number of results on the current page
  * `total_size`: The total number of results across all pages for the current
                  query
* Query information. The specific query information may differ based on the type
  of query. *Address* and *block* query responses contain the original `query`
  as well as a `normalized` representation of the query. *Owner* query responses
  contain the original `query` and a list of `parsed` query components.
  *Account* query responses contain the original 'query'.
* Matched addresses as a list of [Feature](http://geojson.org/geojson-spec.html#feature-objects)
  objects. The `feature` list is sorted by:
  * `street_name`
  * `street_suffix`
  * `street_predir`
  * `street_postdir`
  * `address_low`
  * `address_high`
  * `unit_num` (with `NULL` values first)

Address `Feature` objects contain:
* A `geometry` representing the property. By default, the coordinates are
  longitude, latitude.
* The following list of `properties`:
  * `street_address` (Full address)
  * `address_low`
  * `address_low_suffix`
  * `address_low_frac`
  * `address_high`
  * `street_predir` (e.g., **N** BROAD ST)
  * `street_name` (e.g., N **BROAD** ST)
  * `street_suffix` (e.g., N BROAD **ST**)
  * `street_postdir`
  * `unit_type` (APT, STE, FL, #, UNIT, etc.)
  * `unit_num`
  * `street_full` (e.g., **N BROAD ST**)
  * `zip_code`
  * `zip_4`
  * `usps_bldgfirm' (e.g. "JOHN WANAMAKER FINANCE STATION")
  * `usps_type' (S: Street, H: High-rise, F: Firm)
  * `election_block_id'
  * `election_precinct'  
  * `pwd_parcel_id` (Phila. Water Dept.)
  * `dor_parcel_id` (Dept. of Records)
  * `opa_account_num` (Office of Prop. Assessment)
  * `opa_owners`
  * `opa_address` (Official address, according to OPA)
  * `geom_type` and `geom_source` (metadata about the `geometry` object --
    `geom_type` will be either `"centroid"` or `"parcel"`, and `geom_source`
    will begin with `pwd` or `dor`)


## Queries

You can query the API by address, block, OPA account number, or owner name. All
query's return objects that represent addresses. Any result set can be further
filtered to contain only addresses that have OPA account numbers by using the
`opa_only` querystring parameter.

You can request that units contained within a given property be returned along
with the top-level property by specifying the `include_units` querystring
parameter. This parameter is only relevant for *address* queries.

You can request that the geometry of the address object by returned as coordinates of a particular projection, by specifying the 'srid=####' querystring parameter, where #### is the numeric projection SRID/EPSG. (i.e. http://spatialreference.org/ref/)


**Addresses**

Retrieve addresses that match some address string.

Example:
```bash
curl "https://api.phila.gov/ais/v1/addresses/1234%20Market%20St"\
    -H "Authorization: Gatekeeper-Key abcd1234efab5678cdef9012abcd3456"
```


**Owner**

Retrieve addresses that have owner names matching the query. Queries are treated
as substrings of owner names. You can search for multiple substrings by
separating search terms by spaces.

Examples:
```bash
# Request properties owned by anyone whose first or last name contains "Poe"
curl "https://api.phila.gov/ais/v1/owners/Poe"\
    -H "Authorization: Gatekeeper-Key abcd1234efab5678cdef9012abcd3456"

# Request properties owned by anyone whose first or last name contains "Severus"
# AND whose first or last name contains "Snape" (both conditions must be met)
curl "https://api.phila.gov/ais/v1/owners/Severus%20Snape"\
    -H "Authorization: Gatekeeper-Key abcd1234efab5678cdef9012abcd3456"
```
