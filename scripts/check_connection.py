"""Smoke test: verify env + Supabase Postgres reachable. Use after D02."""

from __future__ import annotations

import sys

import psycopg
from rich.console import Console

from asag.config import ConfigError, get_settings

console = Console()


def main() -> int:  # in CLI program, 0 means success, non-zero -> fail
    cfg = get_settings()

    try:
        db_url = cfg.require_db_url()
    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        return 1

    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn, conn.cursor() as cur:
            cur.execute("select version();")
            row = cur.fetchone()
            console.print(f"[green]Postgres OK[/green] — {row[0] if row else '?'}")

            cur.execute(
                "select default_version from pg_available_extensions where name = 'vector';"
            )
            ext = cur.fetchone()
            if ext:
                console.print(f"[green]pgvector available[/green] — version {ext[0]}")
            else:
                console.print("[yellow]pgvector NOT available[/yellow]")
    except psycopg.OperationalError as e:
        console.print(f"[red]Connection failed:[/red] {e}")
        console.print("[dim]Tip: use Session pooler URL (host has 'pooler.supabase.com').[/dim]")
        return 2  # config OK, but DB connection fail
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Unexpected:[/red] {type(e).__name__}: {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
