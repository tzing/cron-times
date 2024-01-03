from __future__ import annotations

import os

import humanize
from flask import Flask


def create_app():
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE=os.path.join(app.instance_path, "cron-times.sqlite"),
        SITE_NAME="Cron Times",
        TIMETABLE_LOOKBEHIND_SECONDS=86400,
        TIMETABLE_LOOKAHEAD_SECONDS=172800,
    )

    app.config.from_envvar("CRON_TIMES_SETTINGS", silent=True)

    # ensure the instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # register database handler
    import cron_times.db

    app.teardown_appcontext(cron_times.db.close_db)

    # commands
    import cron_times.jobdef
    import cron_times.readers.dbt_cloud

    app.cli.add_command(cron_times.db.command_init_db)
    app.cli.add_command(cron_times.jobdef.command_read_file)
    app.cli.add_command(cron_times.jobdef.init_db_from)
    app.cli.add_command(cron_times.readers.dbt_cloud.read_dbt_cloud)

    # register blueprints
    import cron_times.app

    app.register_blueprint(cron_times.app.bp)

    # register filters
    app.jinja_env.filters["datetime_format"] = datetime_format
    app.jinja_env.filters["naturalday"] = humanize.naturalday
    app.jinja_env.filters["naturaltime"] = humanize.naturaltime

    return app


def datetime_format(value, format="%Y-%m-%d %H:%M:%S"):
    return value.strftime(format)
