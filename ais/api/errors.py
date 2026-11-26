"""JSON error payload formatting for API responses."""

import json

STATUS_CODES = {
    400: "Bad Request",
    404: "Not Found",
    500: "Internal Server Error",
}


def json_error(status: int, message: str | None, details: dict | None = None) -> str:
    """Serialize a standardized API error payload as JSON."""
    error_data = {
        "status": status,
        "error": STATUS_CODES.get(status, ""),
        "message": message,
        "details": {} if details is None else details,
    }
    return json.dumps(error_data)
