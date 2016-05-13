from ais import app

# Importing ais.api will initialize the app's routes.
import ais.api.views

from werkzeug.contrib.profiler import ProfilerMiddleware
app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[10])

if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'])
else:
    application = app