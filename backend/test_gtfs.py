from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

from constants import VEHICLE_POSITION_URL


def _load_env() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(env_path)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    _load_env()

    api_key = os.getenv("ODPT_API_KEY", "").strip()
    if not api_key:
        logging.error("ODPT_API_KEY is not set")
        return 1

    params = {"acl:consumerKey": api_key}
    logging.info("Fetching GTFS-RT via query params")
    response = requests.get(VEHICLE_POSITION_URL, params=params, timeout=(5, 10))
    logging.info("Status: %s", response.status_code)
    response.raise_for_status()
    logging.info("Bytes: %d", len(response.content))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
