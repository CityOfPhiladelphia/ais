import os
from flask_script import Command, Option
#from ais import manager
from flask.cli import FlaskGroup
from flask.cli import with_appcontext

cli = FlaskGroup(app)

@click.command(name='engine')
@with_appcontext
class EngineCommand(Command):
    """Management command for engine scripts."""
    def run(self):
        print('ok')

app.cli.add_command(create)


# Loop over .py files in /scripts

for root, dirs, files in os.walk('./ais/engine/scripts'):
    for file in files:
        if not file.endswith('.py'):
            continue
        name = file[:-3]
        script_path = os.path.abspath(os.path.join(root, file))
        cmd = ScriptCommand(name, script_path)

if __name__ == "__main__":
    cli()
