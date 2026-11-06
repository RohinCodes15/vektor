from collections.abc import Iterable, Mapping
from typing import Any

_REQUEST_LOCATIONS = {"query", "path", "body", "header", "cookie"}


def summarize_errors(errors: Iterable[Mapping[str, Any]]) -> str:
    """One readable line from Pydantic errors. Uses only locations and messages, never input values."""
    parts = []
    for error in errors:
        loc = [str(part) for part in error.get("loc", ())]
        if loc and loc[0] in _REQUEST_LOCATIONS:
            loc = loc[1:]
        message = str(error.get("msg", "Invalid value")).removeprefix("Value error, ")
        parts.append(f"{'.'.join(loc)}: {message}" if loc else message)
    return "; ".join(parts) or "Invalid request"
