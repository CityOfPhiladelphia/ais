# API Usage

[Authentication](#Authentication)

[Queries](#Queries)

[Response Structure & Metadata](#Response Structure & Metadata)

### <a name="Authentication"></a>Authentication

Currently AIS is only designated for internal use. Internal users must request an API key.

## <a name="Queries"></a>Queries

**Endpoints**

There are three API endpoints:

* **Search**: **http://api.phila.gov/ais/v1//search** - Handles a variety of query types, including: 
    * **address** -
    [http://api.phila.gov/ais/v1/search/1234 market st](http://api.phila.gov/ais/v1/search/1234%20market%20st)

    * **block** -
    [http://api.phila.gov/ais/v1/search/1200-1299 block of Market St](http://api.phila.gov/ais/v1/search/1200-1299block%20of%20Market%20St)

    * **intersection** -
    [http://api.phila.gov/ais/v1/search/N 12th and Market St](http://api.phila.gov/ais/v1/search/N%2012th%20and%20Market%20St)

    * **OPA account number** -
    http://api.phila.gov/ais/v1/search/883309050

    * **Regmap ID** -
    http://api.phila.gov/ais/v1/search/001S07-0144    


* **Owner**: **http://api.phila.gov/ais/v1//owner** - retrieves addresses that have owner names matching the query. Queries are treated as substrings of owner names. You can search for multiple substrings by separating search terms by spaces:

      ` Request properties owned by anyone whose first or last name contains "Poe" `
http://api.phila.gov/ais/v1/owner/Poe
    
      ` Request properties owned by anyone whose first or last name contains "Phil" `
      ` AND whose first or last name contains "Lee" (both conditions must be met) `
[http://api.phila.gov/ais/v1/owner/Phil Lee](http://api.phila.gov/ais/v1/owner/phil%20lee)


* **Addresses**: **http://api.phila.gov/ais/v1//addresses** - The original AIS endpoint designed to work with Property Search, this endpoint is being depreciated and replaced by the search endpoint. [http://api.phila.gov/ais/v1/addresses/1234 market st](http://api.phila.gov/ais/v1/search/1234%20market%20st)
    


**Query Flags**

Additional query instructions can be sent via querystring parameters, or flags:

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
  * `search_type`: The query type recognized by Passyunk (address, block, intersection, opa_account, mapreg, or owner) 
  * `search_params`: The querystring parameters or flags and their values included in query
  * `query`: The querystring
  * `normalized`: The querystring normalized by the Passyunk, the AIS backend address parser
  * `type`: "FeatureCollection"
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
  * `type`: "Feature"
  * `ais_feature_type`: The AIS object type represented by the feature (address or interesection)
  * `match_type`: The relationship between the 'normalized' query string and the feature response. Options are:
     * `exact`: Exact match
     * `generic_unit`: Exact but interchanged generic unit_type (APT, UNIT, #, STE) 
     * `base`: Base address match for unit address query
     * `unit_child`: Unit address match for base address query
     * `range-parent`: Ranged_address match for range_child query
     * `range_child`: Range_child match for ranged_address query
     * `unmatched`: Address cannot be matched. Location is estimated from query compoenents. Overlaying service areas are found for estimated location. 
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

