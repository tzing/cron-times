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
    )

    app.config.from_envvar("CRON_TIMES_SETTINGS", silent=True)

    # ensure the instance folder exists
    os.makedirs(app.instance_path, exist_ok=True)

    # register database handler
    import cron_times.db

    app.teardown_appcontext(cron_times.db.close_db)

    # commands
    app.cli.add_command(cron_times.db.command_init_db)

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
