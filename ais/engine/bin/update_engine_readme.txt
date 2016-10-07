The current state of engine building and updating consists of 5 steps:

1. Execute 'build_engine' from the command line

2. Execute 'test_engine' from the command line

3. If all tests pass: continue, else: fix build

4. Execute 'update_db' from the command line

5. Point browser to https://travis-ci.org/ , login and navigate to CityOfPhiladelphia/ais. 
   Open last build and click "Restart Build" in top right corner.