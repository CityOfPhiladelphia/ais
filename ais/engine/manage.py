import os
import sys
import subprocess
from flask_script import Manager
from ais import app

manager = Manager(usage='Perform engine operations')

def path_for_script(root_path, script):
    return os.path.join(root_path, 'engine', 'scripts', script + '.py')

@manager.option('script', help='Name of the script to run, e.g. '
                               '`load_addresses`. Use `all` to run all scripts.'
)
def run(script):
    """Run engine scripts."""
    root_path = app.root_path
    scripts = app.config['ENGINE_SCRIPTS_ALL'] if script == 'all' else [script]
    paths = []

    for script in scripts:
        path = path_for_script(root_path, script)
        if not os.path.isfile(path):
            raise FileNotFoundError('Script not found: {}'.format(script))
        paths.append(path)
        
    for path in paths:
        subprocess.call([sys.executable, path], env=os.environ.copy())

# ACTIVATE BELOW WHEN running "ais db migrate"
#Import database models with app context
# from flask_migrate import Migrate, MigrateCommand
# from ais import app, app_db as db
# with app.app_context():
#   from ais.models import *
#
# migrate = Migrate(app, db)
#
# manager = Manager(app)
# manager.add_command('db', MigrateCommand)
#
# if __name__ == '__main__':
#     manager.run()

app.config['DEBUG'] = True
