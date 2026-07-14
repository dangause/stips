.. _configuration:

Archive Configuration
=====================

Deploymet Configuration
-----------------------

.. _inventory:

Ansible Inventories
^^^^^^^^^^^^^^^^^^^

Inventory files control where Ansible deploys to. For the Lick Searchable Archive we use an "ops" file to define the ops environment.
Other names can be used for development environments.  The ops environment has less debugging information configurated
than development environments.

For ops the current inventory is::

    [all:vars]
    archive_config=ops
    remote_watchdog=False
    # Front end user facing connection info
    frontend_scheme="https"
    frontend_host= "archive.ucolick.org"

    # API access from frontend/backend
    api_scheme=http
    api_server=localhost
    api_port=8000
    # Where ansible should copy from
    archive_source_dir=/home/dusty/work/lick_searchable_archive
    # Connection info Lick Observatory schedule database
    schedule_db_host=schedpsql.ucolick.org
    schedule_db_name=info
    # Set this to "restarted" to restart everything after deploy
    # "stopped" to keep the archive down after deploy
    archive_service_state=restarted

    [frontend]
    # Frontend host. In theory this can be separate from the backend but this has not
    # been tested
    quarry.ucolick.org

    [backend]
    # Backend host
    quarry.ucolick.org

    [backend:vars]
    # Which django apps to install on the backend
    archive_apps=['ingest', 'query', 'archive_admin', 'archive_auth','download']
    # Which systemd services to install on the backend.
    # 'job_queue' : Installs celery and is used for ingesting metadata
    # 'ingest_watchdog': Installs ingest_watchdog.py which watches the archive NFS mount for new files.
    services=['job_queue', 'ingest_watchdog']
    # The type of host.
    # `single_host`: Indicates the archive is installed on a single host
    # 'frontend':    Indicates this is the frontend host in a dual host configuration (not tested)
    # 'backend':     Indicates this is the backend host ina dualhost configuration (not tested)
    host_type=single_host
    gshow_path=/opt/kroot/rel/default/bin/gshow
    # Gunicorn settings for frontend
    frontend_proxy_server="localhost"
    frontend_proxy_port=8000

This is for a single machine configuration.  Theoretically different machines could be used for the frontend and backend but this has not been tested.

.. _host_vars:

Ansible ``host_vars``
^^^^^^^^^^^^^^^^^^^^^
Configuration for a specific machine can be set in a file in the ``host_vars`` directory. For example there's a
file named ``deploy/host_vars/quarry.ucolick.org`` for the ops environment::

    db_data_device: /dev/sdh
    postgres_version: 16
    archive_nfs_source: legion:/data/mthamilton
    archive_nfs_uid: 1009
    archive_nfs_gid: 1039
    archive_data_root: /data/data
    archive_data_mount: /data
    archive_nfs_name: mhadmin
    archive_nfs_group: mhdata
    archive_service_group: stuff
    archive_service_uid: 1002
    archive_service_gid: 1001
    webserver_user: www-data
    webserver_group: stuff
    ssl_cert: /etc/ssl/certs/server_cert.pem
    ssl_private_key: /etc/ssl/private/server_privkey.pem

``db_data_device``
    This is the device that the database storage is available at. Deployment will create a new
    file system for this device, and will mount it to ``/pg_data``.

``postgres_version``
    This is the version of postgres being used. For Ubuntu 24.04 LTS the correct value is "16".

``archive_nfs_source``
    This is the NFS source used to NFS mount the archive's storage. It is added to the fstab to
    mount the storage when the machine boots.

``archive_nfs_uid`` and ``archive_nfs_gid``
    The UID and GID of files stored in the archive storage. Deployment will create users with these
    ids.

``archive_data_root``
    This is the path to the root directory of the data files stored in the archive file system.

``archive_data_mount``
    This is the path to the archive file system is mounted to. This may not be the same as ``archive_data_root`` if
    there is additional non archive data on that file system.

``archive_nfs_name`` and ``archive_nfs_group``
    The user and group names that should own the archive file system NFS mount. They are assigned to ``archive_nfs_uid``
    and ``archive_nfs_gid`` respectively.

``archive_service_group``, ``archive_service_uid``, ``archive_service_gid``
    The user and group to be used for running all services, django apps, and scripts used by the archive.
    This user/group combination should have read permissions to all of the archive data files and directories.

``webserver_user``, ``webserver_group``
    The user and group that the apache virtual host server will run as. This user/group combination
    should have read permissions to all of the archive data files and directories.

``ssl_cert`` and ``ssl_private_key``
    The location of the SSL certs and private key, typically under ``/etc/ssl/certs`` and ``/etc/ssl/private`` respectively.

Ansible defaults
^^^^^^^^^^^^^^^^
The default values for variables used by the Ansible scripts are stored in ``deploy/roles/common/defaults/main.yml``. They
can be overridden by variables in host_vars, or be changed directly before deploying.

``venv_root``
    The root directory where lick archive software is installed. Defaults to ``/opt/lick_archive``

``archive_servie_user`` and ``archive_service_group``
    The user and group used to run archive services including the ingest_watchdog and the django applications.
    Defaults to ``archive``.

``python_version``
    The version of Python in use. Defaults to ``3.12``

``package_install_dir``
    Where Python packages are installed. Defaults to ``{{ venv_root }}/lib/python{{ python_version }}/site-packages``.

``kroot``
   Where KROOT is installed. Defaults to ``/opt/kroot/rel/default/``

``lroot``
    Where LROOT is installed defaults to ``/usr/local/lick/``

``archive_log_dir``
    Where archive software will place any logs. Defaults to ``/var/log/lick_archive``.

``archive_config_dir``
    Where configuration files for archive software are kept. Defaults to ``{{ venv_root }}/etc``.

``watchdog_config``
    The name of the configuration file for the ingest_watchdog. Defaults to ``ingest_watchdog.conf``.

``django_settings``
    The name of the Django settings file. Defaults to ``settings.py``.

``django_secret_keyfile``
    The name of the file storing Django's secret key. This is only created in ops. Defaults to: ``{{ archive_config_dir }}/secret_key``.

``django_log``
    The name of the log file for Django apps. Defaults to ``{{ archive_log_dir }}/lsa_apps.log``

``redis_url``
    The URL for connecting to Redis. Used by Celery.  Defaults to ``redis://localhost:6379/0``

``supported_instrument_dirs``
    The currently supported instrument directories. Defaults to ``['AO', 'shane']``

``frontend_url``
    The URL used to access the archvie frontend, based on variables defined in the inventory file. Defaults to ``{{ frontend_scheme }}://{{ frontend_host }}/{{ archive_url_path_prefix }}``

``default_search_radius``
    The search radius around a point when doing a ra/dec query. Defaults to ``1 arcmin``

``sync_users_cron_minute``
    The minutes portion of the cronjob used to sync users from the schedule database to the archive. Defaults to every two minutes, i.e. ``1-59/2``

Runtime Configuration
---------------------
The runtime configuration files are generated using values in the deployment configuration and live on the archive host.
These can be changed directly but it is recommended to keep any changes synced in the deployment configuration in the
Git repository to prevent changes from being overridden.

.. _archive_config:

Main Archive Configuration File
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The python scripts and django apps read their configuration from :file:`/opt/lick_archive/etc/archive_config.ini`. This
file is generated from the :file:`deploy/roles/common_sw/templates/archive_config.ini.j2` template.

Host Section
++++++++++++

This section holds values specific to this host.

``type``
    The type of host. Acceptable values are ``single_host``, ``frontend``, ``backend``. This value is intended
    for configuring configurations that use separate hosts for the archive's frontend and backend, but
    because this has not been tested it is recommended to only use ``single_host``.

``app_names``
    A comman separated list of apps to deploy to this host. The acceptable values are ``ingest``,
    ``query``, ``archive_admin``, ``archive_auth``, and ``download``.

``url_path_prefix``
    The prefix to use when determining the URL for the API endpoints. This appears after the host and before
    the rest of the path in the URL. Typically this is ``archive`` as in :samp:`https://archive.ucolick.org/{archive}/data`.

``api_url``
    The full URL used to reach the archive's backend API. This is not neccessarilly visible to the outside world.

``frontend_url``
    The full URL used to reach the archive's frontend. This *must* be visible to the outside world.

Database Section
++++++++++++++++

``archive_db``
    The name of the archive's metadata database. Typically ``archive``.

``db_query_user``
    The database user that will be used to query the database by python apps. This
    user only has read-only access to the database. Typically ``archive_query``.

``db_ingest_user``
    The database user that will be used to ingest new metadata into the database. This
    user has read/write privilege to the database. Typically ``archive_ingest``.

Query Section
+++++++++++++

``file_header_url_format``
    A format string used to determine the URL for accessing the header text of a FITS file. It
    is a Python format string, with a ``{}`` that will be replaced by the file's path.

``default_search_radius``
    The default search radius to use when performing coordinate searches and no radius is
    specified in the query.

Ingest Section
++++++++++++++

``archive_root_dir``
    The root directory of archive's file storage.

``supported_directories``
   The supported instrument directories that the archive will scan for new data.

``insert_batch_size``
    How many metadata rows to insert in a single database transaction.

Authorization Section
+++++++++++++++++++++

``default_proprietary_period``
    The default proprietary period for files in the archive. The units can be "day", "days", "month", "months", "year" or "years" and are case insensitivie.
    Foe example "2 years".

``sched_db_host``
    The hostname of the scheduling database server.

``sched_db_name``
    The database name of the scheduling database.

``sched_db_user_info``
    The path to a file containing the login credentials for logging into the scheduling database.

``gshow_path``
    The path to the ``gshoww`` script.

``public_observers``
    Usernames that are considered "public".

``public_ownerhint_pattern``
    Regular expression to match a public ownerhint.

Ingest Watchdog Service
^^^^^^^^^^^^^^^^^^^^^^^
The ingest watchdog service has its own configuration in ``/opt/lick_archive/etc/ingest_watchdog.conf``.
It is generated from the :file:`deploy/roles/ingest_watchdog/templates/ingest_watchdog.conf.j2` template.

``data_root``
    Path to the archive data directory

``startup_resync_age``
    How far back to scan directories when resyncing at start up. Measured in days.

``method``
    The method used to use new files. ``polling`` periodically scans for new files,
    ``inotify`` uses the kernel inotify API but does not work over NFS.

``polling_interval``
    The interval the watchdog will poll the archive directory when using the
    ``polling`` method. In seconds.

``polling_searches``
    A "search" is the name for one of the polling tasks to periodically conduct.
    They are comprised of an interval in seconds, and an age in days indicating
    which directories in the archive to search for new files. These only apply when
    using the ``polling`` method.

    For example, If the current date is 2022-01-10, and the search string is "10:2,60:7":
        * There will be two searches.
        * The first runs every 10 seconds, and searches the directories for
          the dates 2022-01-09 and 2022-01-10.
        * The second runs every 60 seconds, and searches the directories for
          the dates 2022-01-04 through 2022-01-10.

    The searches do not duplicate effort, and may run late if the interval is
    not a multiple of "polling_interval"

``polling_write_delay``
    The polling write delay, controls how long the ``polling`` method waits to notify the archive after
    discovering a file. This gives time for the file to be fully written to disk.


``inotify_age``
    How far back (in days) the watchdoig will look when using the ``inotify`` method will look for new files.

``instrument_dirs``
    The instrument dirs to search. (e.g ``shane``, ``AO``, ``APF``, etc)

``ingest_url``
    The URL for notifying the archive software of new files.

``ingest_retry_max_delay``
    The maximum delay between retries when an error is detected contacting
    the archive's ingest_url. The actual delay is a random number up to this.
    In seconds.

``ingest_retry_max_time``
    The maximum time in seconds to wait while retyring calls to the archive's ingst_url

``ingest_request_timeout``
    How long (in seconds) to wait on a single call to the archive's ingest_url before
    considering it a failure and retrying

Third party configuration files
-------------------------------

The following configuration files configure 3rd party frameworks used to run the archive code. The settings
most interesting for the archive are described below.

Log rotation
^^^^^^^^^^^^
Log rotation is configured in ``/etc/logrotate.d/lick_archive``, which is deployed from the
:file:`deploy/roles/common_sw/templates/archive_logrotate.j2` template. See *man logrotate* for more information.

Python Path
^^^^^^^^^^^
Additional paths for the archive's virtual python environment are in ``/opt/lick_archive/lib/python3.12/site-packages/archive.pth``, which
is deployed from the :file:`deploy/roles/common_sw/templates/archive.pth.j2` template. Currently this allows the
archive to access the ``KROOT`` and ``LROOT`` packages. See `Python's site-specific configuration <https://docs.python.org/3/library/site.html>`_ docs
for more information.

Django Configuration
^^^^^^^^^^^^^^^^^^^^

The django configuration is in ``/opt/lick_archive/etc/settings.py``. Although django actually reads it from
``/opt/lick_archive/lib/python3.12/site-packages/lick_archive/lick_archive_site/settings.py``, which is a symlink.
It is generated from the :file:`deploy/roles/django_site/templates/settings.py.j2` template.

These settings are documented on the `Django project website <https://docs.djangoproject.com/en/5.1/ref/settings/>`_
and the `Django Rest Framework website <https://www.django-rest-framework.org/>`_.

Throttling Rates
++++++++++++++++
We use the Django Rest Framework's throttling to prevent too many download requests from being submitted.
These are controlled with the following settings::

    REST_FRAMEWORK = {
        ...
        # Allow throttling of download API calls to keep users from overwhelming the system.
        'DEFAULT_THROTTLE_CLASSES': [
            'rest_framework.throttling.ScopedRateThrottle',
        ],
        'DEFAULT_THROTTLE_RATES': {
            # Limit it to one request / second. Is that too many?
            'downloads': '1/s'
        },

See the `DRF Throttling docs <https://www.django-rest-framework.org/api-guide/throttling/>`_ for more information.

Logging
+++++++

The ``LOGGING`` dictionary configures how django apps log. Of note the ``filename`` setting defines where the log is placed
and the ``level`` can be changed to ``DEBUG`` for more information.

Database
++++++++
The connection information for the ``archive_django`` database is set in the ``DATABASES`` dictionary.

Celery Configuration
^^^^^^^^^^^^^^^^^^^^
Celery is configured in the ``/opt/lick_archive/etc/celery.env`` file, and by values starting with ``CELERY`` in the Django
``/opt/lick_archive/etc/settings.py`` file.

The ``celery.env`` file is used to configure the systemd service configuration for celery.It is generated from the
:file:`deploy/roles/job_queue/templates/celery.env.j2` template. The main setting that may need to
be changed is ``CELERYD_LOG_LEVEL`` to add more debugging information by changing the level to ``DEBUG``.

See `Celery configuration <https://docs.celeryq.dev/en/stable/userguide/configuration.html#configuration>`_ and
`Celery Daemonization <https://docs.celeryq.dev/en/stable/userguide/daemonizing.html>`_ for more information.

Gunicorn Configuration
^^^^^^^^^^^^^^^^^^^^^^
Gunicorn is configured using ``/opt/lick_archive/etc/gunicorn.conf.py``.  It is generated from the :file:`deploy/roles/django_site/templates/settings.py.j2` template.
See `Gunicorn Settings <https://docs.gunicorn.org/en/latest/settings.html>`_  for more information.

The following Gunicorn settings may be of interest for configuring archive performance and logging.

``workers``
    The number of worker processes used.

``threads``
    The number of threads per worker.

``timeout``
    The timeout for workers to respond to user requests.

``loglevel``
    The logging level in gunicorn logs.

``accesslog``
    The file used for logging every access to gunicorn.

``errorlog``
    The file used for logging gunicorn errors.

Apache Configuration
^^^^^^^^^^^^^^^^^^^^
The archive uses two apache configuration files ``/etc/apache2/sites-available/archive.conf`` defines the virtual hosts the archive uses,
and ``/etc/apache2/ports.conf`` defines the ports apache listens to. These are deployed from the :file:`deploy/roles/webserver/archive.conf.j2` and
:file:`deploy/roles/webserver/ports.conf.j2`` tepmplates.

The archive defines two virtual hosts, one listens on localhost port ``8080`` and is used for ssh tunnel access to the Admin page.
The other listens on port ``443`` and is the main archive webpage.
