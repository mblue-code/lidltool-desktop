from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from lidltool.amazon.recalc import recalculate_amazon_transaction_financials
from lidltool.config import build_config, database_url
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory

app = typer.Typer(help="Amazon transaction finance recalculation")


@app.command("transactions")
def recalc_transactions(
    db: Annotated[
        Path | None,
        typer.Option("--db", help="SQLite database path. Defaults to the app config database."),
    ] = None,
) -> None:
    config = build_config(db_override=db)
    db_url = database_url(config)
    migrate_db(db_url)
    factory = session_factory(create_engine_for_url(db_url))
    with factory() as session:
        result = recalculate_amazon_transaction_financials(session)
        session.commit()
    typer.echo(
        json.dumps(
            {
                "scanned": result.scanned,
                "updated": result.updated,
                "unchanged": result.unchanged,
                "skipped": result.skipped,
                "warnings": list(result.warnings[:20]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
