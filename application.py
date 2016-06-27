from ais import app, manager

# Importing ais.api will initialize the app's routes.
import ais.api.views

if __name__ == '__main__':
    manager.run()
else:
    application = app
