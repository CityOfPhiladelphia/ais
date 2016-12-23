# API Usage

[Authentication](#Authentication)

[Queries](#Queries)

[Response Structure & Metadata](#Response Structure & Metadata)

### <a name="Authentication"></a>Authentication

AIS does not have any authentication on its own, but it is made to sit behind
Philadelphia's [GateKeeper](developer.phila.gov) instance. You must use a GK
API key to access the API. You can sign up for an API key at
https://developer.phila.gov/keys.

Authentication is performed in one of two ways: either with an `Authorization`
header, or with a querystring parameter.  For example, the following would work
as valid requests:

```bash
# Authorization via request header
curl "https://api.phila.gov/ais/v1/search/1234%20Market%20St" \
    -H "Authorization: Gatekeeper-Key abcd1234efab5678cdef9012abcd3456"
```

```bash
# Authorization via querystring parameter
curl "https://api.phila.gov/ais/v1/search/1234%20Market%20St?gatekeeperKey=abcd1234efab5678cdef9012abcd3456"
```

## <a name="Queries"></a>Queries


**Query Types**

The API handles a variety of query types through the **/search** endpoint: 

* **address** - i.e. 
http://api.phila.gov/ais/v1/search/1234%20market%20st
    
* **block** - i.e. 
http://api.phila.gov/ais/v1/search/1200-1299%20block%20of%20Market%20St
    
* **intersection** - i.e. 
http://api.phila.gov/ais/v1/search/N%2012th%20and%20Market%20St
    
* **OPA account number** - i.e. 
http://api.phila.gov/ais/v1/search/883309050
    
* **Regmap ID** - i.e. 
http://api.phila.gov/ais/v1/search/001S07-0144    
   
* **PWD parcel ID** - i.e. 
http://api.phila.gov/ais/v1/search/542611
   
There is an additional **/owner** endpoint for retrieving addresses that have owner names matching the query. Queries are treated as substrings of owner names. You can search for multiple substrings by separating search terms by spaces - i.e.

    # Request properties owned by anyone whose first or last name contains "Poe"
   http://api.phila.gov/ais/v1/owner/Poe
    
    # Request properties owned by anyone whose first or last name contains "Phil"
    # AND whose first or last name contains "Lee" (both conditions must be met)
http://api.phila.gov/ais/v1/owner/phil%20lee
    


**Query Flags**

The API can be sent additional query instructions via querystring parameters, or flags:

* **'opa_only'**: Filters results to contain only addresses that have OPA account numbers.
    
* **'include_units'**: Requests that units contained within a given property be returned along with the top-level property.
    
* **'srid=####'**: Specifies that the geometry of the address object be returned as coordinates of a particular projection, 
     where ####  is the numeric projection SRID/EPSG. (i.e. http://spatialreference.org/ref/)
        
* **'on_curb'**: Specifies that the geometry of the response the best geocode_type on the curb in front of the parcel
    
* **'on_street'**: Specifies that the geometry of the response be the best geocode type on the street in front of the parcel
   
* **'parcel_geocode_location=####'**: Specifies a geocode type to represent the geometry returned in the response. Options are: 

     * 'all', 'pwd_parcel', 'dor_parcel', 'pwd_curb', 'dor_curb', 'pwd_street', 'dor_street', 'true_range', 'centerline'
     * 'parcel_geocode_location' defaults to 'all'



## <a name="Response Structure & Metadata"></a>Response Structure & Metadata

There are currently two distinct json response formats representing address and intersection response objects. Responses for all endpoints are returned in a paginated
[GeoJSON](http://geojson.org/geojson-spec.html) [FeatureCollection](http://geojson.org/geojson-spec.html#feature-collection-objects).

The root of the `FeatureCollection` contains:
* Metadata information.
  * `serach_type`: The type of query 
  * `search_params`:
  * `query`:
  * `normalized`:
  * `type`:
* Pagination information.
  * `page`: The current page of data
  * `page_count`: The total number of pages of data for the current query
  * `page_size`: The number of results on the current page
  * `total_size`: The total number of results across all pages for the current
                  query
* Matched addresses (`Features`) as a list of [Feature](http://geojson.org/geojson-spec.html#feature-objects)
  objects. 

Address `Feature` objects contain:
* The following list of feature metatdata:
  * `type`: Feature
  * `ais_feature_type`: The AIS object type represented by the feature (address or interesection)
  * `match_type`: The relationship between the 'normalized' query string and the object response. Options are:
     * `exact`:
     * `generic_unit`: 
     * `base`: 
     * `unit_child`:
     * `range-parent`:
     * `range_child`:
     * `unmatched`:
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
* The following list of `geometry` attributes:
  * `geocode_type`: 'pwd_parcel', 'dor_parcel', 'pwd_curb', 'dor_curb', 'pwd_street', 'dor_street', 'true_range', or 'centerline'
  * `type`: The geometry type (i.e. Point, Line, Polygon) 
  * `coordinates`: longitude, latitude with default SRID = 4326    

