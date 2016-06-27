from ais import app

# Importing ais.api will initialize the app's routes.
import ais.api.views

if app.config.get('PROFILE', False):
    from werkzeug.contrib.profiler import ProfilerMiddleware
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[30])

if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'])
else:
    application = app
