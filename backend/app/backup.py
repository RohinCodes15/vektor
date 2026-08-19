"""Consistent online backups of Vektor's SQLite databases, safe while the server is running.

    python -m app.backup /data/backups

Copies the portfolio and backtest databases (and the market data cache with --include-cache) into a new timestamped
directory using SQLite's backup API, so a backup never captures a half-written transaction. Paths come from the same
VEKTOR_* settings the server uses. Restore by stopping the server and copying the files back (backend/DEPLOYMENT.md).
"""

import argparse
import logging
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings, get_settings
from app.logging_config import configure_logging

logger = logging.getLogger("vektor.backup")


def backup_databases(settings: Settings, destination: Path, include_cache: bool = False) -> list[Path]:
    """Back up every existing database into destination/<UTC timestamp>/; returns the files written."""
    sources = [settings.portfolio_db_path, settings.backtest_db_path]
    if include_cache:
        sources.append(settings.market_data_cache_path)
    target = destination / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target.mkdir(parents=True, exist_ok=False)
    written = []
    for source in sources:
        if not source.exists():
            logger.warning("database not found; skipped", extra={"path": str(source)})
            continue
        copy = target / source.name
        with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as src, closing(sqlite3.connect(copy)) as dst:
            src.backup(dst)
        written.append(copy)
        logger.info("database backed up", extra={"path": str(copy)})
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up Vektor's SQLite databases.")
    parser.add_argument("destination", type=Path, help="directory that receives a timestamped backup folder")
    parser.add_argument("--include-cache", action="store_true", help="also copy the disposable market data cache")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    written = backup_databases(settings, args.destination, args.include_cache)
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
