from setuptools import setup

setup(name='ais',
      version='0.1',
      description='A platform for geocoding and address-centric data integration',
      url='http://github.com/cityofphiladelphia/ais/',
      author='City of Philadelphia',
      author_email='maps@phila.gov',
      license='MIT',
      packages=['ais'],
      # console_script arg format is <function_name>=<containing_script_name_minus_.py>:<main_function_that_runs_it>
      # See application.py and setup.py for the responsible functions
      #entry_points={'console_scripts': ['ais=ais:cli']},
      entry_points={'console_scripts': ['ais=ais.commands:cli']},
      zip_safe=False)
