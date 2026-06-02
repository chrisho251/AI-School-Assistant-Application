#!/usr/bin/env python3
"""Apply Supabase SQL migrations using psycopg (no psql binary needed).

Usage:
    uv run python scripts/apply_migrations.py
    uv run python scripts/apply_migrations.py --dir custom/migrations/path
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from dotenv import load_dotenv
import psycopg
from rich.console import Console

console = Console()


def apply_migrations(db_url: str, migration_dir: Path) -> bool:
    """Apply all .sql files in migration_dir in sorted order.

    Args:
        db_url:        PostgreSQL connection string.
        migration_dir: Directory containing numbered .sql files.

    Returns:
        True if all migrations succeeded, False on any failure.
    """
    if not migration_dir.is_dir():
        console.print(f"[red]ERROR[/red] Migration directory not found: {migration_dir}")
        return False

    migrations = sorted(migration_dir.glob("*.sql"))
    if not migrations:
        console.print(f"[yellow]WARN[/yellow] No .sql files found in {migration_dir}")
        return True

    console.print(f"[blue]INFO[/blue] Found {len(migrations)} migration(s)")
    console.print()

    succeeded: list[str] = []
    failed: list[str] = []

    # Use a single connection for all migrations — faster, and one TX per file
    try:
        conn = psycopg.connect(db_url)
    except Exception as exc:
        console.print(f"[red]ERROR[/red] Cannot connect to database: {exc}")
        console.print()
        console.print("Check:")
        console.print("  1. SUPABASE_DB_URL is correct in .env")
        console.print("  2. Supabase project is running (https://app.supabase.com)")
        console.print("  3. Network / firewall allows port 5432")
        return False

    with conn:
        for migration_file in migrations:
            console.print(f"  Applying [cyan]{migration_file.name}[/cyan]...", end=" ")
            sql = migration_file.read_text(encoding="utf-8")
            try:
                with conn.transaction():
                    conn.execute(sql)  # type: ignore[arg-type]
                console.print("[green]OK[/green]")
                succeeded.append(migration_file.name)
            except Exception as exc:
                console.print("[red]FAIL[/red]")
                # Strip noise from long Postgres error messages
                msg = str(exc).splitlines()[0]
                console.print(f"    [dim]{msg}[/dim]")
                failed.append(migration_file.name)
                # Continue applying remaining migrations (best-effort — all migrations
                # are idempotent so later files can still succeed independently)

    conn.close()

    # Summary
    console.print()
    console.print("=" * 60)
    for name in succeeded:
        console.print(f"  [green]OK  [/green] {name}")
    for name in failed:
        console.print(f"  [red]FAIL[/red] {name}")
    console.print("=" * 60)

    if failed:
        console.print(f"Result: {len(succeeded)} OK, [red]{len(failed)} FAILED[/red]")
        return False

    console.print(f"Result: [green]{len(succeeded)} migration(s) applied successfully[/green]")
    return True


def main() -> int:
    """CLI entry point."""
    import argparse

    load_dotenv()  # read .env so SUPABASE_DB_URL is available

    parser = argparse.ArgumentParser(
        description="Apply Supabase SQL migrations (uses psycopg, no psql needed).",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("infra/supabase/migrations"),
        help="Migration directory (default: infra/supabase/migrations)",
    )
    args = parser.parse_args()

    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        console.print("[red]ERROR[/red] SUPABASE_DB_URL not set. Add it to your .env file:")
        console.print("  SUPABASE_DB_URL=postgresql://user:password@host:5432/postgres")
        return 1

    # Log connection target (hide password)
    safe_url = db_url.split("@")[-1]  # host:port/db only
    console.print(f"[dim]DB[/dim] {safe_url}")

    success = apply_migrations(db_url, args.dir)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
