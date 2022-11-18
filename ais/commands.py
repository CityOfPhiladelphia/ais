import click
from flask import Flask
from flask.cli import FlaskGroup

def create_app():
    app = Flask('testing')
    # other setup
    return app

@click.group(cls=FlaskGroup, create_app=create_app)
def cli():
    print('Test success!')
    """Management script for the Wiki application."""
