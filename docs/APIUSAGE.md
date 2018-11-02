# API Usage

Welcome to the documentation for AIS API Version 1.0. This document explains how to use version 1.0 of the API. 
* In general, applications supporting user-defined input and interactive maps should use the [/search](#Search) endpoint, which handles a variety of query types by identifying the type and routing to the appropriate endpoint. 
* The [/owner](#Owner) endpoint can be used to search for addresses by owner name.
* The [/service_areas](#ServiceAreas) endpoint can be used for a quick service area lookup by coordinates.
* Otherwise, individual endpoints may be used to minimize overhead associated with routing. More information about individual endpoints can be obtained by exploring our [swagger at the API root](http://api.phila.gov/ais_doc/v1/?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf).    

# <a name="Authentication"></a>Authentication

Currently AIS is only designated for internal use.  Please request an API key so we can monitor your application's API usage to make sure your needs are being met.

### To obtain a key: 
 1.  Email ithelp@phila.gov to create a new support ticket, and copy maps@phila.gov on the email.
 2.  Request that IT Help route the ticket to CityGeo.
 3.  Describe the application that will be using AIS and provide a URL if possible.
 
### To use a key:
 * Add the querystring parameter ```gatekeeperKey=#```, where # is the api key:
 [https://api.phila.gov/ais/v1/search/1234%20Market%20St?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf](https://api.phila.gov/ais_doc/v1/search/1234%20Market%20St?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)
 
 * Alternatively, an `Authorization` header can be used with `curl`:
 
```curl "https://api.phila.gov/ais/v1/search/1234%20Market%20St" -H "Authorization: Gatekeeper-Key 6ba4de64d6ca99aa4db3b9194e37adbf"```
  
# <a name="Queries"></a>Queries

## <a name="Endpoints"></a>Endpoints

The API endpoints are:
* [Search](#Search) - http://api.phila.gov/ais/v1/search
* [Owner](#Owner) - http://api.phila.gov/ais/v1/owner
* [Addresses](#Addresses) - http://api.phila.gov/ais/v1/addresses
* [Service Areas](#ServiceAreas) - http://api.phila.gov/ais/v1/service_areas


### <a name="Search"></a>**Search**
`/search` is a resource which handles a variety of query types, including:

   * **address** - Represents a particular address - 
    [http://api.phila.gov/ais/v1/search/1234 market st](http://api.phila.gov/ais_doc/v1/search/1234%20market%20st?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)

   * **block** - Represents all addresses on a particular block; inputted as range of addresses followed by 'block of' and then street name (with pre-direction) -
    [http://api.phila.gov/ais/v1/search/1200-1299 block of Market St](http://api.phila.gov/ais_doc/v1/search/1200-1299%20block%20of%20Market%20St?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)

   * **intersection** - Inputted as 'street 1 and street 2', including pre-directions, i.e.
    [http://api.phila.gov/ais/v1/search/N 12th and Market St](http://api.phila.gov/ais_doc/v1/search/N%2012th%20and%20Market%20St?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)

   * **OPA account number** - Office of Property Assessment Account Number - 
    [http://api.phila.gov/ais/v1/search/883309050](http://api.phila.gov/ais_doc/v1/search/883309050?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)

   * **Regmap ID** - This is the Department of Records Registry Map ID - 
    [http://api.phila.gov/ais/v1/search/001S07-0144](http://api.phila.gov/ais_doc/v1/search/001S07-0144?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)   
    
   * **coordinates** - Location in x, y format, either as:
     * Geographic WG84 coordinates (srid=4326): [http://api.phila.gov/ais/v1/reverse_geocode/-75.16097658476633, 39.951661655671955](http://api.phila.gov/ais_doc/v1/reverse_geocode/-75.16097658476633,39.951661655671955?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf), or
     * Projected NAD83 / Pennsylvania South (ftUS) (srid=2272): [http://api.phila.gov/ais_test/v1/reverse_geocode/2694253.78730206, 235887.921013063](http://api.phila.gov/ais_doc/v1/reverse_geocode/2694253.78730206,235887.921013063?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)
   
```
   Coordinate searches are routed to the /reverse_geocode endpoint which finds the nearest address 
   to queried coordinates based on address geocodes projected on the curb. True/full range geocodes 
   are also searched against to incorporate addresses not listed in DOR or PWD parcel records.
   Searches are limited within the default search radius of 300 ft unless specified explicitly in the
   request using search_radius=# query flag.
```



### <a name="Owner"></a>__**Owner**__ 
`/owner` is a resource which handles queries of owner names, retrieving addresses that have owner names matching the query. 
* Queries are treated as substrings of owner names:
 * Request properties owned by anyone whose first or last name contains "Poe" - [http://api.phila.gov/ais/v1/owner/Poe](http://api.phila.gov/ais_doc/v1/owner/Poe?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)
* You can search for multiple substrings by separating search terms by spaces:
 * Request properties owned by anyone whose first or last name contains "Phil" AND whose first or last name contains "Lee" (both conditions must be met) - [http://api.phila.gov/ais/v1/owner/Phil Lee](http://api.phila.gov/ais_doc/v1/owner/phil%20lee?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)


### <a name="Addresses"></a>__**Addresses**__ 
`/addresses` is the original AIS endpoint designed to work with [Property Search](http://property.phila.gov/): 
* [http://api.phila.gov/ais/v1/addresses/1234 market st](http://api.phila.gov/ais_doc/v1/search/1234%20market%20st?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)


## <a name="Query Flags"></a>Query Flags

Additional query instructions can be sent via querystring parameters, or flags:

* `opa_only`: Filters results to contain only addresses that have OPA account numbers:
  *  [http://api.phila.gov/ais/v1/search/1234 Market St?opa_only](http://api.phila.gov/ais_doc/v1/search/1234%20Market%20St?opa_only&gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)
    
* `include_units`: Requests that units contained within a given property be returned along with the top-level property:
  *  [http://api.phila.gov/ais/v1/search/1234 Market St?include_units](http://api.phila.gov/ais_doc/v1/search/1234%20Market%20St?include_units&gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)
 
* `srid=#`: Specifies that the geometry of the address object be returned as coordinates of a particular projection, 
     where #  is the numeric projection [SRID/EPSG](http://spatialreference.org/ref/): 
  * Responses without the `srid` flag in the request default to WGS84 coordinates (SRID=4326)
  * State Plane: [http://api.phila.gov/ais/v1/search/1234 Market St?srid=2272](http://api.phila.gov/ais_doc/v1/search/1234%20Market%20St?srid=2272&gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)
        
* `on_curb`: Specifies that the geometry of the response be the best geocode type on the curb in front of the parcel:
  * [http://api.phila.gov/ais/v1/search/1234 Market St?on_curb](http://api.phila.gov/ais_doc/v1/search/1234%20Market%20St?on_curb&gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)    
   
* `on_street`: Specifies that the geometry of the response be the best geocode type on the street in front of the parcel:
  * [http://api.phila.gov/ais/v1/search/1234 Market St?on_street](http://api.phila.gov/ais_doc/v1/search/1234%20Market%20St?on_street&gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)   
 
* `parcel_geocode_location`: Requests that a feature for [each type of address geocode geometry](#geocode_type) be returned:
  * [http://api.phila.gov/ais/v1/search/1234 Market St?parcel_geocode_location](http://api.phila.gov/ais_doc/v1/search/1234%20Market%20St?parcel_geocode_location&gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)   
 
* `search_radius=#`: Specifies a custom search radius for reverse geocoding, where # is the user defined radius in feet:
  * [http://api.phila.gov/ais/v1/reverse_geocode/2734283 294882?search_radius=750](http://api.phila.gov/ais_doc/v1/reverse_geocode/2734283%20294882?search_radius=750&gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)
  * `*note`: A user defined search_radius is limited to a maximum of 10,000 feet.


# <a name="Response Structure & Metadata"></a>Response Structure & Metadata

 There are currently two distinct json response formats representing [address](#Address) and [intersection](#Intersection) response objects. Responses for all endpoints are returned in a paginated [GeoJSON](http://geojson.org/geojson-spec.html) [FeatureCollection](http://geojson.org/geojson-spec.html#feature-collection-objects). 

## <a name="Pagination"></a>Pagination

 Responses for all endpoints are returned in a paginated [GeoJSON](http://geojson.org/geojson-spec.html) [FeatureCollection](http://geojson.org/geojson-spec.html#feature-collection-objects).  A maximum of 100 features are returned per page. Use the querystring parameter ```page=#```, where # is the page number, to specify a particular page of features to be returned in the response:
 * [http://api.phila.gov/ais/v1/search/2401 pennsylvania ave?include_units&opa_only&page=2](http://api.phila.gov/ais_doc/v1/search/2401%20pennsylvania%20ave?include_units&opa_only&page=2&gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)
 
A pagination object is returned in the [response envelope](#Envelope) detailing the ```page``` number of the response.


## <a name="Envelope"></a>The Envelope

The root of the `FeatureCollection` contains:
* **Metadata** information.
  * `search_type`: The query type recognized by Passyunk (address, block, intersection, opa_account, mapreg, pwd_parcel_id, or owner) 
  * `search_params`: The querystring parameters or flags and their values included in query
  * `query`: The querystring
  * `normalized`: The querystring normalized by the Passyunk, the AIS backend address parser
  * `crs`: coordinate reference system metadata
  ```json
     {
        "properties": {
           "href": "link to metadata about the spatial reference system used in the response",
           "type": "proj4",
         },
         "type": "link",
    }
  ```
  } 
  * `type`: "FeatureCollection"
  
* **Pagination** information.
  * `page`: The current page of data
  * `page_count`: The total number of pages of data for the current query
  * `page_size`: The number of results on the current page
  * `total_size`: The total number of results across all pages for the current
                  query
* Matched address or intersection (`Features`) as a list of [Feature](http://geojson.org/geojson-spec.html#feature-objects)
  objects. Please note, more than one feature may be returned as an `exact` match (see below).

## <a name="AIS Feature Types"></a>AIS Feature Types

### <a name="Address"></a>**Address**
* The following list of feature metadata:
  * `type`: "Feature"
  * `ais_feature_type`: The AIS object type represented by the feature (address or interesection)
  * `match_type`: The relationship between the 'normalized' query string and the feature response. Options are:
     * `exact`: Exact match
     * `generic_unit`: Exact but interchanged generic unit_type (APT, UNIT, #, STE)
     * `unit_sibling`: Base address match but different unit types/numbers between matched and queried address
     * `has_base`: Base address match for unit address query
     * `unit_child`: Unit address match for base address query
     * `in_range`: Range_child match for ranged address query     
     * `overlaps`: Range address match by range overlapping queried ranged_address range 
     * `range-parent`: Ranged_address match for in-range query
     * `has_base_unit_child`: Base address unit child match
     * `has_base_in_range`: In-range base address match for ranged unit address query 
     * `has_base_overlaps`: Overlapping ranged base address match for ranged unit address query
     * `in_range_unit_child`: In-range unit address match for ranged address query
     * `range_parent_unit_child`: Ranged address unit child match for in-range query
     * `on_block`: Returned via block search
     * `contains_query_string`: Returned via owner search
     * `exact_location`: Returned via reverse geocode search
     * `exact_key`: Returned via pwd_parcel id, regmap id, or property account number query
     * `unmatched`: Address cannot be matched. Location is estimated from query components. Overlaying service areas are found for estimated location. 
* The following list of `properties`:
  * `street_address` (Full address)
  * `address_low` (**1234** MARKET ST)
  * `address_low_suffix` (e.g. 4131**R** RIDGE AVE)
  * `address_low_frac`  (e.g. 503 **1/2** FITZWATER ST)
  * `address_high` (e.g. 1608-**16** POPLAR ST)
  * `street_predir` (e.g., **N** BROAD ST)
  * `street_name` (e.g., N **BROAD** ST)
  * `street_suffix` (e.g., N BROAD **ST**)
  * `street_postdir` (e.g. 190 N INDEPENDENCE MALL **W**)
  * `unit_type` (APT, STE, FL, #, UNIT, etc.)
  * `unit_num`
  * `street_full` (e.g., **N BROAD ST**)
  * `zip_code`
  * `zip_4`
  * `usps_bldgfirm` (e.g. "JOHN WANAMAKER FINANCE STATION")
  * `usps_type` (S: Street, H: High-rise, F: Firm)
  * `election_block_id`
  * `election_precinct`  
  * `pwd_parcel_id` (Phila. Water Dept.)
  * `dor_parcel_id` (Dept. of Records)
  * `li_address_key` (Licenses & Inspections)
  * `eclipse_location_id` (Licenses & Inspections)
  * `bin` (Licenses & Inspections)
  * `opa_account_num` (Office of Prop. Assessment)
  * `opa_owners`
  * `opa_address` (Official address, according to OPA)
* The following list of `geometry` attributes:
  * <a name="geocode_type"></a>`geocode_type` - Possible options are:
    * `pwd_parcel` - The PWD parcel centroid
    * `dor_parcel` - The DOR parcel centroid
    * `pwd_curb` - The PWD parcel centroid projected on the curb
    * `dor_curb` - The DOR parcel centroid projected on the curb
    * `pwd_street` - The PWD parcel projected on the street (midpoint between centerline and curb)
    * `dor_street` - The DOR parcel projected on the street (midpoint between centerline and curb)
    * `true_range` - The address number position interpolated along the actual range of addresses related to a street segment centerline 
    * `full_range` - The address number position interpolated along the full range of addresses related to a street segment centerline
  * `type`: The geometry type (i.e. Point, Line, Polygon) 
  * `coordinates`: longitude, latitude with default SRID = 4326    
* The following list of `service areas`:
  * `center_city_district`
  * `cua_zone`
  * `li_district`
  * `philly_rising_area`
  * `census_tract_2010`
  * `census_block_group_2010`
  * `census_block_2010`
  * `council_district_2016`
  * `political_ward`
  * `political_division`
  * `planning_district`
  * `elementary_school`
  * `middle_school`
  * `high_school`
  * `zoning`
  * `zoning_rco`
  * `commercial_corridor`
  * `police_division`
  * `police_district`
  * `police_service_area`
  * `rubbish_recycle_day`
  * `recycling_diversion_rate`
  * `leaf_collection_area`
  * `sanitation_area`
  * `sanitation_district`
  * `sanitation_convenience_center`
  * `clean_philly_block_captain`
  * `historic_street`
  * `highway_district`
  * `highway_section`
  * `highway_subsection`
  * `traffic_district`
  * `traffic_pm_district`
  * `street_light_route`
  * `pwd_maint_district`
  * `pwd_pressure_district`
  * `pwd_treatment_plant`
  * `pwd_water_plate`
  * `pwd_center_city_district`
  * `major_phila_watershed`
  * `litter_schema_test`
  * `neighborhood_advisory_committee`
  * `ppr_friends`

### <a name="Intersection"></a>**Intersection**
* The following list of feature metadata:
  * `type`: "Feature"
  * `ais_feature_type`: The AIS object type represented by the feature (address or intersection)
  * `match_type`: The relationship between the 'normalized' query string and the feature response. Options are:
     * `exact`: Exact match
* The following list of `properties`:
     * `int_id`: the intersection id as assigned by Streets
     * `street_1`: properties for street_1 are:
        * `street_code`: 5 digit numeric unique code associated with each unique street name
        * `street_full`: full street (including predir, postdir and suffix)
        * `street_name`:  street name
        * `street_predir`: street cardinal pre-direction
        * `street_postdir`: street post-direction
        * `street_suffix`: street suffix 
     * `street_2`: properties for street_2 are:
        * `street_code`: 5 digit numeric unique code associated with each unique street name
        * `street_full`: full street (including predir, postdir and suffix)
        * `street_name`:  street name
        * `street_predir`: street cardinal pre-direction
        * `street_postdir`: street post-direction
        * `street_suffix`: street suffix 

## <a name="StatusCodes"></a>Status Codes
API calls having an identifiable search type return a response with a `200 status`, structured as an envelope wrapping a feature collection of either address or intersection feature type(s), as described above. The 200 status is understood and a status key is not contained in the response. Please note, a 200 response does not validate an address; the returned [match_type](#ais-feature-types) signifies the relationship of the query to the response.

A `404 status` is returned when:

 * the search type is not recognized, 
 ```json
    {
       "status": 404,
       "error": "Not Found",
       "message": "Query not recognized.",
       "details": {
       "query": "a b c d"
       }
    }
```

 * there query is too long, or 
 ```json
    {
       "status": 404,
       "error": "Not Found",
       "message": "Query exceeds character limit.",
       "details": {
           "query": "1234 market stttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttttt"
       }
    }
```

 * there is a known issue with its relationship to a real address

```json
    {
        "status": 404,
        "error": "Not Found",
        "message": "Address number is out of range.",
        "details": {
            "query": "50000 market st"
        }
    }
```


## <a name="Additional Resources"></a>Additional Resources
### <a name="ServiceAreas"></a>__**Service Areas**__ 
`/service_areas` is a resource which returns service areas that overlay the queried location. To search by coordinates, please enter in x, y format, either as:
* Geographic WG84 coordinates (srid=4326): [http://api.phila.gov/ais/v1/service_areas/-75.16097658476633, 39.951661655671955](http://api.phila.gov/ais_doc/v1/service_areas/-75.16097658476633,%2039.951661655671955?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf), or
* Projected NAD83 / Pennsylvania South (ftUS) (srid=2272): [http://api.phila.gov/ais/v1/service_areas/2694253.78730206, 235887.921013063](http://api.phila.gov/ais_doc/v1/service_areas/2694253.78730206,%20235887.921013063?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf)

The `/service_areas` endpoint response contains the query metadata, geometry and crs objects, as well the service area data. The response format is:


  * `search_type`: 'coordinates'
  * `search_params`: No search parameters are currently being handled by this endpoint.
  * `query`: x, y
  * `normalized`: The querystring normalized by the Passyunk, the AIS backend address parser. Passyunk normalizes coordinate inputs to x,y format with 6 decimal places.
  * `crs`: coordinate reference system metadata
  
  ```json
     {
        "properties": {
           "href": "link to metadata about the spatial reference system used in the response",
           "type": "proj4",
         },
         "type": "link",
    }
  ```
  
  * `service_areas`:
    * `center_city_district`
    * `cua_zone`
    * `li_district`
    * `philly_rising_area`
    * `census_tract_2010`
    * `census_block_group_2010`
    * `census_block_2010`
    * `council_district_2016`
    * `political_ward`
    * `political_division`
    * `planning_district`
    * `elementary_school`
    * `middle_school`
    * `high_school`
    * `zoning`
    * `zoning_rco`
    * `commercial_corridor`
    * `police_division`
    * `police_district`
    * `police_service_area`
    * `rubbish_recycle_day`
    * `recycling_diversion_rate`
    * `leaf_collection_area`
    * `sanitation_area`
    * `sanitation_district`
    * `sanitation_convenience_center`
    * `clean_philly_block_captain`
    * `historic_street`
    * `highway_district`
    * `highway_section`
    * `highway_subsection`
    * `traffic_district`
    * `traffic_pm_district`
    * `street_light_route`
    * `pwd_maint_district`
    * `pwd_pressure_district`
    * `pwd_treatment_plant`
    * `pwd_water_plate`
    * `pwd_center_city_district`
    * `major_phila_watershed`
    * `litter_schema_test`
    * `neighborhood_advisory_committee`
    * `ppr_friends`

* `geometry`:
  * `geocode_type`: 'input'
  * `type`: 'Point'
  * `coordinates`: x, y in the same spatial reference system as the inputted coordinates (either 4326 or 2272)

