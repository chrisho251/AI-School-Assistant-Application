"""Run the FastAPI app with a psycopg-compatible event loop on Windows.

uvicorn hardcodes Windows' ProactorEventLoop in its loop factory (see
``uvicorn/loops/asyncio.py``), which psycopg's async pool rejects. Rather than
let uvicorn build the loop, this launcher drives ``Server.serve()`` on a
SelectorEventLoop via ``asyncio.run(..., loop_factory=...)`` (Python 3.12+).

Usage:
    uv run python scripts/run_api.py               # 127.0.0.1:8000
    uv run python scripts/run_api.py --port 8001
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ASAG API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    config = uvicorn.Config("asag.api.main:app", host=args.host, port=args.port)
    server = uvicorn.Server(config)

    # On Windows, force the SelectorEventLoop (psycopg async is incompatible with
    # the ProactorEventLoop uvicorn would otherwise pick). loop_factory needs 3.12+.
    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
