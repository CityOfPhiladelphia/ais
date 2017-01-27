# API Usage

Welcome to the documentation for AIS API Version 1.0. This document explains how to use version 1.0 of the API. 
* In general, applications supporting user-defined input and interactive maps should use the [/search](#Search) endpoint, which handles a variety of query types by identifying the type and routing to the appropriate endpoint. 
* The [/owner](#Owner) endpoint can be used to search for addresses by owner name.
* Otherwise, individual endpoints may be used to minimize overhead associated with routing. More information about individual endpoints can be obtained by exploring our [swagger at the API root](http://api.phila.gov/ais/v1).    

# <a name="Authentication"></a>Authentication

Currently AIS is only designated for internal use.  Please request an API key so we can monitor your application's API usage to make sure your needs are being met.

### To obtain a key: 
 1.  Send a request-ticket to the IT help desk
 2.  cc: maps.phia.gov
 3.  Request that the help desk 'please route to GSG'
 4.  Describe the application and provide a url if possible
 
### To use a key:
 * Add the querystring parameter ```gatekeeperKey=#```, where # is the api key:
 https://api.phila.gov/ais/v1/search/1234%20Market%20St?gatekeeperKey=6ba4de64d6ca99aa4db3b9194e37adbf
 
 * Alternatively, an `Authorization` header can be used with `curl`:
 
```curl "https://api.phila.gov/ais/v1/search/1234%20Market%20St" -H "Authorization: Gatekeeper-Key 6ba4de64d6ca99aa4db3b9194e37adbf"```
  
# <a name="Queries"></a>Queries

## <a name="Endpoints"></a>Endpoints

The API endpoints are:
* [Search](#Search) - http://api.phila.gov/ais/v1/search
* [Owner](#Owner) - http://api.phila.gov/ais/v1/owner
* [Addresses](#Addresses) - http://api.phila.gov/ais/v1/addresses


### <a name="Search"></a>**Search**
`\search` is a resource which handles a variety of query types, including:

   * **address** - Represents a particular address - 
    [http://api.phila.gov/ais/v1/search/1234 market st](http://api.phila.gov/ais/v1/search/1234%20market%20st)
    
   * **address range** - Represents all addresses within a particular address range; inputted as a range of addresses followed by street name (with predirection). This search type is currently under development. 
   [http://api.phila.gov/ais/v1/search/1200-1234 Market St](http://api.phila.gov/ais/v1/search/1200-1234%20Market%20St)

   * **block** - Represents all addresses on a particular block; inputted as range of addresses follewed by 'block of' and then street name (with predirection) - 
    [http://api.phila.gov/ais/v1/search/1200-1299 block of Market St](http://api.phila.gov/ais/v1/search/1200-1299%20block%20of%20Market%20St)

   * **intersection** - Inputted as 'n street 1 and street 2', including predirections, i.e.
    [http://api.phila.gov/ais/v1/search/N 12th and Market St](http://api.phila.gov/ais/v1/search/N%2012th%20and%20Market%20St)

   * **OPA account number** - Office of Property Assessment Account Number - 
    http://api.phila.gov/ais/v1/search/883309050

   * **Regmap ID** - This is the Department of Records Registry Map ID - 
    http://api.phila.gov/ais/v1/search/001S07-0144    


### <a name="Owner"></a>__**Owner**__ 
`\owner` is a resource which handles queries of owner names, retrieving addresses that have owner names matching the query. 
* Queries are treated as substrings of owner names:
 * Request properties owned by anyone whose first or last name contains "Poe" - http://api.phila.gov/ais/v1/owner/Poe
* You can search for multiple substrings by separating search terms by spaces:
 * Request properties owned by anyone whose first or last name contains "Phil" AND whose first or last name contains "Lee" (both conditions must be met) - [http://api.phila.gov/ais/v1/owner/Phil Lee](http://api.phila.gov/ais/v1/owner/phil%20lee)


### <a name="Addresses"></a>__**Addresses**__ 
`\addresses` is the original AIS endpoint designed to work with [Property Search](http://property.phila.gov/): 
* [http://api.phila.gov/ais/v1/addresses/1234 market st](http://api.phila.gov/ais/v1/search/1234%20market%20st)
    


## <a name="Query Flags"></a>Query Flags

Additional query instructions can be sent via querystring parameters, or flags:

* `opa_only`: Filters results to contain only addresses that have OPA account numbers:
 *  [http://api.phila.gov/ais/v1/search/1234 Market St?opa_only](http://api.phila.gov/ais/v1/search/1234%20Market%20St?opa_only)
    
* `include_units`: Requests that units contained within a given property be returned along with the top-level property:
 *  [http://api.phila.gov/ais/v1/search/1234 Market St?include_units](http://api.phila.gov/ais/v1/search/1234%20Market%20St?include_units)
 
* `srid=#`: Specifies that the geometry of the address object be returned as coordinates of a particular projection, 
     where #  is the numeric projection [SRID/EPSG](http://spatialreference.org/ref/): 
 * Responses without the `srid` flag in the request default to WGS84 coordinates (SRID=4326)
 * State Plane: [http://api.phila.gov/ais/v1/search/1234 Market St?srid=2272](http://api.phila.gov/ais/v1/search/1234%20Market%20St?srid=2272)
        
* `on_curb`: Specifies that the geometry of the response be the best geocode type on the curb in front of the parcel:
 * [http://api.phila.gov/ais/v1/search/1234 Market St?on_curb](http://api.phila.gov/ais/v1/search/1234%20Market%20St?on_curb)    
   
* `on_street`: Specifies that the geometry of the response be the best geocode type on the street in front of the parcel:
 * [http://api.phila.gov/ais/v1/search/1234 Market St?on_street](http://api.phila.gov/ais/v1/search/1234%20Market%20St?on_street)   
 
* `parcel_geocode_location`: Requests that a feature for [each type of address geocode geometry](#geocode_type) be returned:
 * [http://api.phila.gov/ais/v1/search/1234 Market St?parcel_geocode_location](http://api.phila.gov/ais/v1/search/1234%20Market%20St?parcel_geocode_location)   


## <a name="Pagination"></a>Pagination

 Responses for all endpoints are returned in a paginated [GeoJSON](http://geojson.org/geojson-spec.html) [FeatureCollection](http://geojson.org/geojson-spec.html#feature-collection-objects).  A maximum of 100 features are returned per page. Use the querystring parameter ```page=#```, where # is the page number, to specify a particular page of features to be returned in the response:
 * [http://api.phila.gov/ais/v1/search/2401 pennsylvania ave?include_units&opa_only&page=2](http://api.phila.gov/ais/v1/search/2401%20pennsylvania%20ave?include_units&opa_only&page=2)
 
A pagination object is returened in the [response envelope](#The Envelope) detailing the ```page``` number of the response.


# <a name="Response Structure & Metadata"></a>Response Structure & Metadata

 There are currently two distinct json response formats representing [address](#Address) and [intersection](#Intersection) response objects. Responses for all endpoints are returned in a paginated
 [GeoJSON](http://geojson.org/geojson-spec.html) [FeatureCollection](http://geojson.org/geojson-spec.html#feature-collection-objects).

## <a name="The Envelope"></a>The Envelope

The root of the `FeatureCollection` contains:
* **Metadata** information.
  * `search_type`: The query type recognized by Passyunk (address, block, intersection, opa_account, mapreg, or owner) 
  * `search_params`: The querystring parameters or flags and their values included in query
  * `query`: The querystring
  * `normalized`: The querystring normalized by the Passyunk, the AIS backend address parser
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
* The following list of feature metatdata:
  * `type`: "Feature"
  * `ais_feature_type`: The AIS object type represented by the feature (address or interesection)
  * `match_type`: The relationship between the 'normalized' query string and the feature response. Options are:
     * `exact`: Exact match
     * `generic_unit`: Exact but interchanged generic unit_type (APT, UNIT, #, STE) 
     * `base`: Base address match for unit address query
     * `unit_child`: Unit address match for base address query
     * `range-parent`: Ranged_address match for range_child query
     * `range_child`: Range_child match for ranged_address query
     * `unmatched`: Address cannot be matched. Location is estimated from query components. Overlaying service areas are found for estimated location. 
     * `parsed`: Address cannot be matched and location cannot be estimated. Response includes parsed street components and null geometry.
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
  * `usps_bldgfirm` (e.g. "JOHN WANAMAKER FINANCE STATION")
  * `usps_type` (S: Street, H: High-rise, F: Firm)
  * `election_block_id`
  * `election_precinct`  
  * `pwd_parcel_id` (Phila. Water Dept.)
  * `dor_parcel_id` (Dept. of Records)
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
  * `police_division`
  * `police_district`
  * `police_service_area`
  * `rubbish_recycle_day`
  * `recycling_diversion_rate`
  * `leaf_collection_area`
  * `sanitation_area`
  * `sanitation_district`
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

### <a name="Intersection"></a>**Intersection**
* The following list of feature metatdata:
  * `type`: "Feature"
  * `ais_feature_type`: The AIS object type represented by the feature (address or interesection)
  * `match_type`: The relationship between the 'normalized' query string and the feature response. Options are:
     * `exact`: Exact match
     * `parsed`: Intersection cannot be matched and location cannot be estimated. Response includes parsed street components and null geometry.
* The following list of `properties`:
     * `street_1`: properties for street_1 are:
        * `street_code`: 5 digit numeric unique code associated with each unique street name
        * `street_full`: full street (includeing predir, postdir and suffix)
        * `street_name`:  street name
        * `street_predir`: street cardinal pre-direction
        * `street_postdir`: street post-direction
        * `street_suffix`: street suffix 
     * `street_2`: properties for street_2 are:
        * `street_code`: 5 digit numeric unique code associated with each unique street name
        * `street_full`: full street (includeing predir, postdir and suffix)
        * `street_name`:  street name
        * `street_predir`: street cardinal pre-direction
        * `street_postdir`: street post-direction
        * `street_suffix`: street suffix 

## <a name="Status Codes"></a>Status Codes
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
