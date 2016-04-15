import json
from collections import OrderedDict


class AddressJsonSerializer:
    def model_to_data(self, address):
        data = OrderedDict([
            ('street_address', address.street_address),
            ('address_low', address.address_low),
            ('address_low_suffix', address.address_low_suffix),
            ('address_low_frac', address.address_low_frac),
            ('address_high', address.address_high),
            ('street_predir', address.street_predir),
            ('street_name', address.street_name),
            ('street_suffix', address.street_suffix),
            ('street_postdir', address.street_postdir),
            ('unit_type', address.unit_type),
            ('unit_num', address.unit_num),
            ('street_full', address.street_full),
        ])
        return data

    def render(self, data):
        return json.dumps(data)

    def serialize(self, address):
        data = self.model_to_data(address)
        return self.render(data)

    def serialize_many(self, addresses):
        data = [self.model_to_data(address) for address in addresses]
        return self.render(data)