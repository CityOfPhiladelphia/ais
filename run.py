from ais import app

# Importing ais.api will initialize the app's routes.
import ais.api.views

app.run(debug=app.config['DEBUG'])
