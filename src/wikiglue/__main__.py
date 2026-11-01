from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from . import app
from .config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="wikiglue")
    parser.add_argument("-c", "--config", type=Path, default=Path("/etc/wikiglue/wikiglue.toml"))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    if config.matrix is None:
        raise SystemExit(f"{args.config}: no [matrix] section; nothing to do")

    # Everything (Matrix client, aiohttp session) is created inside the running loop.
    asyncio.run(app.run(config))


if __name__ == "__main__":
    main()
