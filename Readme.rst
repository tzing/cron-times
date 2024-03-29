Cron-times
==========

.. image:: https://img.shields.io/pypi/v/cron-times
   :alt: PyPI - Version

Cron-times is the timetable for your cronjobs.
It shows you when your cronjobs are running, in a human-friendly way.

.. image:: ./screenshot.png
   :alt: Screenshot of cron-times


Quick start
-----------

Install from PyPI:

.. code-block:: bash

    pip install cron-times

Run:

.. code-block:: bash

   flask --app cron_times init-db
   flask --app cron_times run

The app will be available at http://localhost:5000


Add cronjobs
------------

You can describe your cronjobs in TOML format:

.. code-block:: toml

   # Always starts with [[job]]
   # You can add multiple jobs in one file
   [[job]]

   # unique key within the group for each job
   # this field is invisible to users and only used for internal reference
   # if not set, it will use job name as the key
   key = "custom-key-01"

   # [required] job name
   name = "Sample job"

   # [required] cronjob schedule, in crontab format
   schedule = "0 10/3 * * *"

   # timezone, default to UTC
   timezone = "Asia/Taipei"

   # job description
   description = """
   In the description, you *can* use `markdown`
   """

   # flag to indicate if the job is enabled
   enabled = true

   # labels
   labels = [
      "foo",
   ]

   # metadata
   # you can use this field to store any extra information
   [job.metadata]
   "extra field" = "can be anything"
   pi = 3.14
   "reference url" = "https://example.com"

After the TOML file is ready, you can import it with the following command:

.. code-block:: bash

   flask --app cron_times read-file /path/to/jobs.toml


Built-in job adapters
---------------------

Cron-times comes with some built-in job adapters.
You can use them by running the following commands and it will read the job list from the specified location.

dbt cloud
+++++++++

Reads schedule job list from `dbt cloud`_:

.. code-block:: bash

   flask --app cron_times read-dbt-cloud --help

.. _dbt cloud: https://docs.getdbt.com/docs/cloud/about-cloud/dbt-cloud-features

Argo workflow
+++++++++++++

Reads `Cron Workflows`_ from `Argo Workflows`_:

.. code-block:: bash

   flask --app cron_times read-argo-workflow --help

.. _Cron Workflows: https://argoproj.github.io/argo-workflows/cron-workflows/
.. _Argo Workflows: https://argoproj.github.io/argo-workflows/


Configuration
-------------

Cron-times uses `Flask`_ as the web framework, and adapts Flask's configuration system.

Set the environment variable to the path of that file:

.. code-block:: bash

   export CRON_TIMES_SETTINGS=/path/to/settings.cfg

You can set the following options:

.. code-block:: cfg

   # Site name to be used for the page title
   SITE_NAME="My cronjobs"

   # Time range to show in the timetable based on current time, in seconds
   TIMETABLE_LOOKBEHIND_SECONDS=86400  # 1day
   TIMETABLE_LOOKAHEAD_SECONDS=172800  # 2days

   # Max number of items to show in the timetable
   # If there are more items than this number, it would only return the jobs that is closest to the current time
   # Note that the more items you show, the slower the page will be loaded
   TIMETABLE_MAX_ITEMS=512

.. _Flask: https://flask.palletsprojects.com/en/3.0.x/
