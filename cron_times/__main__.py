from pathlib import Path

import click

from cron_times.utils import dump, setup_logging


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
    "-o",
    "--output",
    type=click.Path(exists=False, file_okay=True, dir_okay=False, path_type=Path),
    show_default=True,
    default="tasks/crontab.yaml",
    help="File to output or update.",
)
@click.option(
    "--user",
    help="Specify the username whose crontab to read.",
)
@click.option(
    "--overwrite", is_flag=True, help="Overwrite the output file when it exists."
)
def crontab(output: Path, user: str, overwrite: bool):
    """Read crontab and output to file."""
    from cron_times.providers.crontab import get_tasks

    setup_logging()
    tasks = get_tasks(user=user)
    dump(output, overwrite, tasks)


if __name__ == "__main__":
    cli()
