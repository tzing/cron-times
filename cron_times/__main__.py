from pathlib import Path

import click


@click.group()
def cli():
    ...


@cli.command()
@click.option(
    "-h",
    "--host",
    default="127.0.0.1",
    help="Hostname to listen on.",
    show_default=True,
)
@click.option(
    "-p",
    "--port",
    type=click.INT,
    default=5000,
    help="Port to listen.",
    show_default=True,
)
def serve(host: str, port: int):
    """Run server in dev mode.

    Note: for production, use a production WSGI server instead."""
    import cron_times

    cron_times.app.run(host=host, port=port, debug=True)


@cli.group()
def get_tasks():
    """Fetch cronjobs."""
    ...


@get_tasks.command()
@click.option(
    "--file",
    type=click.Path(exists=False, file_okay=True, dir_okay=False, path_type=Path),
    show_default=True,
    default="tasks/dbt.yaml",
    help="File to output or update.",
)
@click.option("--account-id", required=True, type=click.INT, help="Account id")
@click.option(
    "--token",
    required=True,
    envvar="DBT_TOKEN",
    help="API token. Could be provided from env var `DBT_TOKEN`.",
)
@click.option(
    "-p",
    "--project-id",
    type=click.INT,
    help="Only select task(s) in this project. "
    "You can set this option multiple times. All tasks would be included when on set",
)
def dbt(account_id: int, token: str):
    """Get cronjobs from dbt."""
    import cron_times.providers.dbt

    tasks = cron_times.providers.dbt.get_tasks(account_id=account_id, token=token)


if __name__ == "__main__":
    cli()
