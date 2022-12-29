# Timetable for cronjobs

Show schdueled jobs in a more readable way.

![screenshot](./screenshot.png)


## Usage

1. Install

   ```bash
   pip install git+https://github.com/tzing/cron-times.git
   ```

2. Create job definition files

   Job definition are YAML files placed under `jobs/` folder in current working directory.

   An example job:

   ```yaml
   - name: Job name
     schedule: "0 10 * * *"
     timezone: Asia/Taipei  # tzdata format; Would use UTC if not provided
     description: In the description, you *can* use `markdown`
     labels:
       - sample-label
       - another-label
   ```

   All `*.yaml` files would be loaded on initialization time.
   We could build some code to pull the defines from other places before flask started.

4. Run the app

   ```bash
   flask --app cron_times run
   ```
