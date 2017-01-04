# API Usage

[Authentication](#Authentication)

[Queries](#Queries)

[Response Structure & Metadata](#Response Structure & Metadata)

## <a name="Authentication"></a>Authentication

Currently AIS is only designated for internal use.  Internal users must request an API key.

## <a name="Queries"></a>Queries

**Endpoints**

The API endpoints are:
* [Search](#Search) - http://api.phila.gov/ais/v1/search
* [Owner](#Owner) - http://api.phila.gov/ais/v1/owner
* [Addresses](#Addresses) - http://api.phila.gov/ais/v1/addresses


<a name="Search"></a>**Search** - is a resource whilch handles a variety of query types, including: 

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


<a name="Owner"></a>__**Owner**__ - is a resource which handles queries of owner names, retrieving addresses that have owner names matching the query. Queries are treated as substrings of owner names. You can search for multiple substrings by separating search terms by spaces:

* Request properties owned by anyone whose first or last name contains "Poe" - http://api.phila.gov/ais/v1/owner/Poe
* Request properties owned by anyone whose first or last name contains "Phil" AND whose first or last name contains "Lee" (both conditions must be met) - [http://api.phila.gov/ais/v1/owner/Phil Lee](http://api.phila.gov/ais/v1/owner/phil%20lee)


<a name="Addresses"></a>__**Addresses**__ is the original AIS endpoint designed to work with [Property Search.](http://property.phila.gov/) This endpoint is being depreciated and replaced by the search endpoint. [http://api.phila.gov/ais/v1/addresses/1234 market st](http://api.phila.gov/ais/v1/search/1234%20market%20st)
    


**Query Flags**

Additional query instructions can be sent via querystring parameters, or flags:

* **opa_only**: Filters results to contain only addresses that have OPA account numbers.
    
* **include_units**: Requests that units contained within a given property be returned along with the top-level property.
    
* **srid=####**: Specifies that the geometry of the address object be returned as coordinates of a particular projection, 
     where ####  is the numeric projection SRID/EPSG. (i.e. http://spatialreference.org/ref/)
        
* **on_curb**: Specifies that the geometry of the response be the best geocode type on the curb in front of the parcel
    
* **on_street**: Specifies that the geometry of the response be the best geocode type on the street in front of the parcel
   
* **parcel_geocode_location**: Requests that a feature for [each type of address geocode geometry](#geocode_type) be returned. 



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
