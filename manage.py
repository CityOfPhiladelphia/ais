import os
from flask_script import Command, Option
from ais import manager

class EngineCommand(Command):
    """Management command for engine scripts."""
    def run(self):
        print('ok')

manager.add_command('engine', EngineCommand)


# Loop over .py files in /scripts

for root, dirs, files in os.walk('./ais/engine/scripts'):
    for file in files:
        if not file.endswith('.py'):
            continue
        name = file[:-3]
        script_path = os.path.abspath(os.path.join(root, file))
        cmd = ScriptCommand(name, script_path)

manager.run()
