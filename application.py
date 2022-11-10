from ais import app as application

# Importing ais.api will initialize the app's routes.
import ais.api.views

if __name__ == '__main__':
    cli = FlaskGroup(application)
    cli()
