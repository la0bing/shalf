"""``shalf-console``: run the console (API + UI)."""

from __future__ import annotations

import argparse
import os

import uvicorn

from shalf_console.app import create_app
from shalf_console.settings import ConsoleSettings


def main() -> None:
    parser = argparse.ArgumentParser(prog="shalf-console")
    parser.add_argument("--config", default=os.getenv("SHALF_CONSOLE_CONFIG"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8090")))
    args = parser.parse_args()
    uvicorn.run(
        create_app(ConsoleSettings.load(args.config)),
        host=args.host,
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
