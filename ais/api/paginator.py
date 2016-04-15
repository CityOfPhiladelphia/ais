from collections import OrderedDict
from functools import lru_cache
from math import ceil


PAGE_SIZE = 100


class Paginator:
    def __init__(self, collection, max_page_size=PAGE_SIZE):
        self.collection = collection
        self.max_page_size = max_page_size

    @property
    @lru_cache()
    def collection_size(self):
        return self.collection.count()

    @property
    @lru_cache()
    def page_count(self):
        return ceil(self.collection_size / self.max_page_size)

    def get_page(self, page):
        return self.collection\
            .offset((page - 1) * self.max_page_size)\
            .limit(self.max_page_size)

    def get_page_size(self, page=None):
        if page and page < self.page_count:
            return self.max_page_size
        else:
            return self.collection_size % self.max_page_size

    def get_page_info(self, page):
        return OrderedDict([
            ('page', page),
            ('page_count', self.page_count),
            ('page_size', self.get_page_size(page)),
            ('total_size', self.collection_size),
        ])
