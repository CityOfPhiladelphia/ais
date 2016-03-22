from setuptools import setup

setup(name='ais',
      version='0.1',
      description='A platform for geocoding and address-centric data integration',
      url='http://github.com/cityofphiladelphia/ais/',
      author='City of Philadelphia',
      author_email='maps@phila.gov',
      license='MIT',
      packages=['ais'],
      entry_points={'console_scripts': ['ais=ais:manager.run']},
      zip_safe=False)