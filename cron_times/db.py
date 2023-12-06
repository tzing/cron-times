from __future__ import annotations

import sqlite3

import click
import flask


def get_db() -> sqlite3.Connection:
    if "db" not in flask.g:
        flask.g.db = sqlite3.connect(
            flask.current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )

        sqlite3.paramstyle = "named"

    return flask.g.db


def close_db(e=None) -> None:
    db = flask.g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    with flask.current_app.open_resource("schema.sql", mode="r") as fd:
        db.executescript(fd.read())


@click.command("init-db")
def init_db_command() -> None:
    """Initialize the database."""
    init_db()
    click.echo("Database initialized")
