# Cron-times

[![PyPI version](https://img.shields.io/pypi/v/cron-times)](https://pypi.org/project/cron-times/)

Cron-times is the timetable for your cronjobs. It shows you when your cronjobs will run, in a human readable view.

![screenshot](./screenshot.png)

* Setup job list in YAML format
* Timezone supported - Able to configure server timezone and show the time in local time

## Install

```bash
pip install cron-times
```

## Usage

Cron-times is an [Flask] application. You can run it with the following commands:

```bash
flask --app cron_times init-db
flask --app cron_times run
```

The server will be running on http://localhost:5000

[Flask]: https://flask.palletsprojects.com/en/3.0.x/

### Add job(s)

There is no job listed by default.
You can describe your cronjobs in YAML format:

```yaml
# Optional group name; if not set, it will use the filename
group: Sample group

# Job list
jobs:

  - # Unique key within the group for each job
    # This field is invisible to users and only used for internal reference
    # If not set, it will use job name as the key
    key: sample-task
    # Job name
    name: Sample task
    # Cronjob schedule, in crontab format
    schedule: "0 10/3 * * *"
    # Optional timezone, default to UTC
    timezone: Asia/Taipei
    # Optional job description
    description: In the description, you *can* use `markdown`
    # Optional labels
    labels:
      - foo
    # Optional metadata
    # You can use this field to store any extra information
    metadata:
      extra metadata: can be anything
    # Optional flag to indicate if the job is enabled
    # If not set, it will be recognized as enabled
    enabled: true
```

After the YAML file is ready, you can import it with the following command:

```bash
flask --app cron_times read-file /path/to/jobs.yaml
```


## Configuration

It uses Flask's configuration system. Set the environment variable to the path of that file:

```bash
export CRON_TIMES_SETTINGS=/path/to/settings.cfg
```

You can set the following options:

```cfg
SITE_NAME="My cronjobs"
```
