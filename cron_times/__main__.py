from pathlib import Path

import click

from cron_times.utils import dump, setup_logging, update_task_definition


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
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
    required=True,
    default="tasks/crontab.yaml",
    show_default=True,
    help="File to output or update.",
)
@click.option("--user", help="Specify the username whose crontab to read.")
@click.option(
    "-l",
    "--label",
    default=("crontab",),
    multiple=True,
    help="Label(s) to put on these tasks.",
)
@click.option(
    "--overwrite", is_flag=True, help="Overwrite the output file when it exists."
)
def crontab(output: Path, user: str, label: list, overwrite: bool):
    """Read crontab and output to file.

    The file would be completely overwritten when `--overwrite` is given.
    """
    from cron_times.providers.crontab import get_tasks

    setup_logging()
    tasks = get_tasks(user=user, labels=label)
    dump(output, overwrite, tasks)


@get_tasks.command()
@click.argument("account_id", type=click.INT)
@click.option(
    "-t",
    "--token",
    envvar="DBT_TOKEN",
    required=True,
    help="Token to access dbt cloud API.",
)
@click.option(
    "-p",
    "--project-id",
    type=click.INT,
    multiple=True,
    help="Only select tasks from these project(s).",
)
@click.option(
    "-e",
    "--environment-id",
    type=click.INT,
    multiple=True,
    help="Only select tasks from these environment(s).",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(exists=False, file_okay=True, dir_okay=False, path_type=Path),
    required=True,
    default="tasks/dbt.yaml",
    show_default=True,
    help="File to output or update.",
)
@click.option(
    "-l",
    "--label",
    default=("dbt",),
    multiple=True,
    help="Label(s) to put on these tasks.",
)
@click.option(
    "-u",
    "--update-field",
    type=click.Choice(["name", "schedule", "description", "labels"], False),
    show_default=True,
    default=("name", "schedule"),
    multiple=True,
    help="Update these fields",
)
@click.option(
    "--keep-untracked",
    is_flag=True,
    help="Keep all task definitions in the file. "
    "Or it removes tasks that are not present on dbt cloud by default.",
)
def dbt(
    account_id: int,
    token: str,
    project_id: tuple[int, ...],
    environment_id: tuple[int, ...],
    output: Path,
    label: tuple[str, ...],
    update_field: bool,
    keep_untracked: bool,
):
    """Read tasks from dbt cloud and update to file.

    This command update the selected fields and keep the rest data and comments
    upchanged."""
    from cron_times.providers.dbt import get_tasks

    setup_logging()
    tasks = get_tasks(account_id, token, project_id, environment_id, label)
    update_task_definition(output, "_id", tasks, update_field, keep_untracked)


if __name__ == "__main__":
    cli()
