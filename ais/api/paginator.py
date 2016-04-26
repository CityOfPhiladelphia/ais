from collections import OrderedDict
from functools import lru_cache
from math import ceil
from sqlalchemy.orm.query import Query


PAGE_SIZE = 100


class Paginator:
    def __init__(self, collection, max_page_size=PAGE_SIZE):
        self.collection = collection
        self.max_page_size = max_page_size

    @property
    @lru_cache()
    def collection_size(self):
        return len(self.collection)

    @property
    @lru_cache()
    def page_count(self):
        return ceil(self.collection_size / self.max_page_size)

    def get_page(self, page):
        start = (page - 1) * self.max_page_size
        end = start + self.max_page_size
        return self.collection[start:end]

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

    class ValidationError (Exception):
        def __init__(self, message, data):
            super().__init__()
            self.message = message
            self.data = data

    def validate_page_num(self, page_num_str):
        # Figure out which page the user is requesting
        try:
            page_num = int(page_num_str)
        except ValueError:
            raise self.ValidationError('Invalid page value.', {'page': page_num_str})

        # Page has to be less than the available number of pages
        page_count = self.page_count
        if page_num < 1 or page_num > page_count:
            raise self.ValidationError('Page out of range.',
                               {'page': page_num, 'page_count': page_count})

        return page_num



class QueryPaginator (Paginator):
    @property
    @lru_cache()
    def collection_size(self):
        return self.collection.count()

    def get_page(self, page):
        return self.collection\
            .offset((page - 1) * self.max_page_size)\
            .limit(self.max_page_size)
