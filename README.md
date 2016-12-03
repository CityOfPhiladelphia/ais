# Address Information System (AIS)

AIS provides a unified view of City data for an address.

## Goals

- Simplify relationships between land records, real estate properties, streets, and addresses
- Provide a way of standardizing addresses citywide
- Support applications that require geocoding and address-based data lookups
- Provide a feedback mechanism for continually improving parity between department datasets
- Deprecate legacy systems for geocoding and address standardizing

## Components

- geocoder
- address standardizer (see [passyunk](https://github.com/cityofphiladelphia/passyunk))
- integration environment for address-centric data
- API

## Development

To develop locally:

1. `git clone https://github.com/CityOfPhiladelphia/ais`
2. `cd ais`
3. Create and activate a [virtualenv](https://virtualenv.pypa.io/en/stable/).
4. `pip install -r requirements.txt`. You may have to work through installing some dependencies by hand, especially on Windows.
5. Copy [Passyunk](https://github.com/cityofphiladelphia/passyunk) data files. See README for more instructions.
6. Create an empty file at `/ais/instance/config.py`. To run engine scripts, you'll need to add dictionary to this called `DATABASE` mapping database names to connection strings. (TODO: commit sample instance config)
7. Rename `.env.sample` in the root directory to `.env` and add real environment settings. (TODO: commit `.env.sample`)
8. `honcho start`
