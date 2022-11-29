from os.path import dirname, basename, isfile, join
import glob
# Load everything in this directory as an importable sub module
# so it can be called by ais/engine/commands.py
modules = glob.glob(join(dirname(__file__), "*.py"))
__all__ = [ basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py')]
