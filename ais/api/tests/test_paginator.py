# Test that addresses are sorted in order by default

# Test that results are geocoded in the correct priority order

# Test that invalid page values raise 400

# Test that empty results return a 404

import pytest
from ..views import validate_page_param
from ..paginator import Paginator

@pytest.fixture
def full_paginator():
    return Paginator([1, 2, 3, 4, 5, 6, 7, 8], max_page_size=3)

@pytest.fixture
def page_request():
    class MockRequest:
        pass
    request = MockRequest()
    request.args = {}
    return request

def test_first_page_validation(page_request, full_paginator):
    """
    `validate_page_param` returns an error of `None` when there is
    content and page is `'1'`.
    """
    page_request.args = {'page': '1'}
    page, error = validate_page_param(page_request, full_paginator)
    assert error is None
    assert page == 1

def test_last_page_validation(page_request, full_paginator):
    page_request.args = {'page': '3'}
    page, error = validate_page_param(page_request, full_paginator)
    assert error is None
    assert page == 3

def test_negative_page_validation(page_request, full_paginator):
    page_request.args = {'page': '-1'}
    page, error = validate_page_param(page_request, full_paginator)
    assert error

def test_out_of_bound_page_validation(page_request, full_paginator):
    page_request.args = {'page': '4'}
    page, error = validate_page_param(page_request, full_paginator)
    assert error

def test_non_numeric_page_validation(page_request, full_paginator):
    page_request.args = {'page': 'blah'}
    page, error = validate_page_param(page_request, full_paginator)
    assert error

def test_page_count(page_request, full_paginator):
    assert full_paginator.page_count == 3

def test_first_page_size(page_request, full_paginator):
    assert full_paginator.get_page_size(1) == 3

def test_last_page_size(page_request, full_paginator):
    assert full_paginator.get_page_size(3) == 2
