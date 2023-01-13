import click
import cron_times


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
    cron_times.app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    cli()
