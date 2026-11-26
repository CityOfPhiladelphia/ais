"""Collection and SQLAlchemy Query pagination helpers."""

from functools import lru_cache
from math import ceil

PAGE_SIZE = 100


class Paginator:
    """Paginates across one or more sliceable collections."""

    def __init__(self, *collections, max_page_size: int = PAGE_SIZE):
        self.collections = collections
        self.max_page_size = max_page_size

    @property
    @lru_cache()
    def collection_sizes(self) -> tuple[int, ...]:
        return tuple(len(c) for c in self.collections)

    @property
    @lru_cache()
    def collection_size(self) -> int:
        return sum(self.collection_sizes)

    @property
    @lru_cache()
    def page_count(self) -> int:
        return ceil(self.collection_size / self.max_page_size)

    def get_page(self, page: int):
        start = (page - 1) * self.max_page_size
        end = start + self.max_page_size

        for collection, size in zip(self.collections, self.collection_sizes):
            if start < size:
                partial_page = tuple(collection[start:end])
                partial_size = len(partial_page)
                yield from partial_page
                start = 0
                end -= partial_size
            else:
                start -= size
                end -= size

            if end <= 0:
                break

    def get_page_size(self, page: int | None = None) -> int:
        if self.collection_size == 0:
            return 0
        if page and page < self.page_count:
            return self.max_page_size
        remainder = self.collection_size % self.max_page_size
        return remainder if remainder != 0 else self.max_page_size

    def get_page_info(self, page: int) -> dict[str, int]:
        return {
            "page": page,
            "page_count": self.page_count,
            "page_size": self.get_page_size(page),
            "total_size": self.collection_size,
        }

    class ValidationError(Exception):
        def __init__(self, message: str, data: dict):
            super().__init__(message)
            self.message = message
            self.data = data

    def validate_page_num(self, page_num_str: str) -> int:
        try:
            page_num = int(page_num_str)
        except ValueError:
            raise self.ValidationError("Invalid page value.", {"page": page_num_str})

        page_count = self.page_count
        if page_num < 1 or page_num > page_count:
            raise self.ValidationError(
                "Page out of range.",
                {"page": page_num, "page_count": page_count},
            )

        return page_num


class QueryPaginator(Paginator):
    """Paginates SQLAlchemy Query objects using SQL OFFSET/LIMIT."""

    @property
    @lru_cache()
    def collection_sizes(self) -> tuple[int, ...]:
        return tuple(c.count() for c in self.collections)

    def get_page(self, page: int):
        offset = (page - 1) * self.max_page_size
        limit = self.max_page_size

        for collection, size in zip(self.collections, self.collection_sizes):
            if offset < size:
                partial_page = tuple(collection.offset(offset).limit(limit))
                partial_size = len(partial_page)
                yield from partial_page
                offset = 0
                limit -= partial_size
            else:
                offset -= size

            if limit <= 0:
                break
