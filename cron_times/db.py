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
    db.executescript(
        """
        DROP TABLE IF EXISTS job;

        CREATE TABLE job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            "group" TEXT,
            key TEXT,

            name TEXT NOT NULL,
            schedule TEXT NOT NULL,
            timezone TEXT NOT NULL DEFAULT 'UTC',
            description TEXT,
            labels TEXT,
            metadata TEXT,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            UNIQUE ("group", key)
        );
        """
    )


@click.command("init-db")
def init_db_command() -> None:
    """Initialize the database."""
    init_db()
    click.echo("Database initialized")
