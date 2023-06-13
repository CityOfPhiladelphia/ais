import pytest

# Add pytest option to allow us to pass test names to skip
def pytest_addoption(parser):
    parser.addoption("--skip", action="store", default=None,
                     help="Specify tests to skip by providing a comma-separated list of test names.")

# Loop through passed --skip value and remove tests from being run
def pytest_collection_modifyitems(config, items):
    # Get the list of test names to skip from the command line
    skip_tests = config.getoption("--skip")
    if skip_tests:
        # Split the comma-separated list of test names into a list
        skip_list = [test.strip() for test in skip_tests.split(",")]
        # Filter out the tests that are in the skip list
        deselected = []
        for item in items:
            if item.nodeid.split("::")[-1] in skip_list:
                item.add_marker(pytest.mark.skip(reason="Skipped because --skip option was provided"))
                deselected.append(item)
        # Remove the deselected tests from the item list
        for item in deselected:
            items.remove(item)
