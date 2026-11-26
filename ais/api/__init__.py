"""AIS WSGI API package — exposes `app` with all HTTP routes registered."""

from ais import app
import ais.api.views  # noqa: F401 - registers API routes on `app`

__all__ = ["app"]
