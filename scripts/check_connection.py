"""Smoke test: verify env + Supabase Postgres reachable. Use after D02."""

from __future__ import annotations

import sys

import psycopg
from rich.console import Console

from asag.config import get_settings

console = Console()


def main() -> int:
    cfg = get_settings()
    if not cfg.supabase_db_url:
        console.print("[red]SUPABASE_DB_URL not set in .env[/red]")
        return 1

    try:
        with psycopg.connect(cfg.supabase_db_url) as conn, conn.cursor() as cur:
            cur.execute("select version();")
            row = cur.fetchone()
            console.print(f"[green]Postgres OK[/green] — {row[0] if row else '?'}")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Connection failed:[/red] {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
