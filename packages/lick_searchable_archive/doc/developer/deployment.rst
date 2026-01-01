.. _deployment:

Deployment
==========

The lick searchable archive is deployed using `Ansible <https://www.ansible.com/>`_. This requires
a development/deployment machine that has ansible on it. This machine should be separate from the
host that will run the archive.

Setting up a Development/Deployment Machine
--------------------------------------------
Use ``conda`` or ``venv`` to setup a deployment machine to create a distinct python environment::

    conda create -n archive python=3.12
    conda activate archive

    *or*

    python3.12 -m venv archive
    source archive/bin/activate

Then install packages needed for unit testing::

    pip install pytest
    pip install django
    pip install astropy
    pip install sqlalchemy
    pip install djangorestframework
    pip install psycopg2-binary
    pip install tenacity
    pip install coverage
    pip install passlib

Packages needed for external tests (in test/ext_test)::

    pip install requests

Packages needed for building the frontend::

    pip install docutils
    sudo apt install npm
    npm install --save-exact --save-dev esbuild

Packages needed for deploying::

    sudo apt install ansible

Packages needed for building developer docs::

    pip install sphinx


In addition the following packages are not used on the development machine, but might be good to install
to keep IDEs looking for imports happy::

    pip install Celery

Quality of Life packages::

    pip install ipython

.. _deploy-requirements:

Requirements for deploying the archive
--------------------------------------
    * A host for the archive software

      * This host must use Ubuntu 24.04 as its OS.
      * This host must have a user, with sudo access, that can ssh to the target machine without being prompted for a password.
      * This host should have at least 8 GiB of memory.
      * The software host requires a database data partition of at least 128GiB (Which will be formatted and mounted during the deployment).

    * A host providing the archive data

      * The archive data must be exported to the software host via NFS. Only read-only access is required. The ansible deployment
        will update the archive host's ``/etc/fstab`` to mount it.


Configuring the Deployment
--------------------------

1. Install SSL certs

    The ansible installation epects SSL certs to already be installed on the archive webserver. Install the certs into ``/etc/ssl/certs/``
    and the private key into ``/etc/ssl/private/``.  The actual name of the certs do not matter as they match the Ansible :ref:`host variables <host_vars>`.

    If the SSL certs do not appear to be working, it may be neccessary to open the certs file and manually reverse the order of certs within the file.

2. Ansible Inventory

    Create or configure an ansible inventory. This will control where the archive is deployed to and other configuration information.
    See :ref:`Inventory <inventory>` for more information.

3. Host Variables

    Create or configure ansible host variables for deploying. This configures host specific things and user/group ids.
    See :ref:`Host Variables <host_vars>` for more information.

4. Schedule Database User

    To avoid putting database password information into source code, any files with sensitive information
    are stored in the ``deploy/data`` directory in a subdirectory named after the ansible inventory.
    For example ``deploy/data/ops``. Currently only one file is deployed this way: ``sched_db_user_info``. This
    file stores the login information for the schedule database used to help determine ownership of proprietary data.
    To create this file run::

        $ cat '<user_name>:<password>' > deploy/data/ops/sched_db_user_info

    Replace ops with the correct inventory name.

    Ansible deploys this file to ``/opt/lick_archive_etc/sched_db_user_info`` on the target host.

Building the Frontend
---------------------
Before deploying the archive, the frontend must be built::

    $ cd lick_searchable_archive/frontend
    $ make all


Deploying
---------
Ansible is a declaritive tool: you define how the system *should* be and it tries to make that happen.
This means it will only run changes that are needed. For example if PostgreSQL is already installed it will not re-install it.
Running ansible twice is safe and will just verify that everything worked. Only the ``single_host_archive.yml`` ansible playbook
is needed to deploy the archive. However, this can be time consuming if only a portion of the archive needs to  be deployed.
To alleviate this additional playbooks are provided to install portions of the archive.


Deploying everything to a single machine
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Deploying everything to a single machine can be done in one command::

    ansible-playbook  single_host_archive.yml -i  your_env -u your_user -K

`your_env` in the above command is the inventory file described earlier that lists the machines
being deployed to.  `your_user` is a user on the target machine with that meets the requirements
stated in :ref:`deploy-requirements`. This will prompt you for the password ``your_user`` uses
for sudo access on the target machine.

For example::

    ansible-playbook  single_host_archive.yml -i  ops -u localdusty -K

``your_user`` should be able to  ssh to the target machine without being challenged for a password.
If neccessary it is possible to specify a specific ssh key to use for this. For example::

    ansible-playbook  single_host_archive.yml -i ops --key-file ~/work/keys/id_quarry_localdusty -u localdusty -K


Deploying portions of the Archive
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
During development and testing it is useful to be able to deploy only a portion of the archive. The following ansible playbooks are provided to do so.

``admin_scripts.yml``
Installs the admin scripts intended to be run at the command line by administrators.

``dbservers.yml``
  Installs the PostgreSQL database software and related administrative software. Also makes sure the database data parition is formatted and mounted.

``django_apps.yml``
  Installs the python code for the archive's Django applications.

``django_site.yml``
  Installs the Gunicorn proxy service used to serve django apps, along with the apps themselves and the
  django configuration.

``frontend.yml``
  Installs the Apache webserver, the archive virtual host, and archive frontend.

``ingest_watchdog.yml``
  Installs the ingest_watchdog systemd service.

``webserver.yml``
  Installs the apache webserver and the archive virtual host.

Post Deployment Steps
---------------------

Backend Host
^^^^^^^^^^^^^

``KROOT`` and ``LROOT`` must be installed on the backend software host. See :ref:`Installation Notes <installation_notes>` for the example configuration files.

For ``KROOT`` instructions see the ``HowToKroot`` documentation. For ``LROOT`` Use the following commands::

    $ cd cvs/lroot
    $ make bootstrap
    $ cd schedule
    $ make install


Metadata Database
+++++++++++++++++
On a fresh environment, the deployment will create the ``archive`` database but will not create the schema.
This is to allow the administrator to restore a previous database or create a new one.
See :ref:`Database Administration <db_admin>` for how to do this.


Django Database
+++++++++++++++
The Django environment will also need to be created. Use these commands to do so::

    $ source /opt/lick_archive/bin/activate

    # For new database only
    $ manage.py makemigrations archive_auth
    $ manage.py makemigrations ingest

    # For both new and updated
    $ manage.py migrate

User Sync
+++++++++
Make sure the external schheduling database host will accept connections from archive database host. To do so inspect
``/var/log/lick_archive/sync_archive_users.log``. You should see something like::

    ...
    INFO     2025-03-11 21:15:02.855 pid:16663 sync_archive_users:create_user:296 Creating user obid:1946/brsafdi@berkeley.edu
    INFO     2025-03-11 21:15:02.855 pid:16663 sync_archive_users:create_user:296 Creating user obid:1947/rbowru@ucsc.edu
    INFO     2025-03-11 21:15:02.910 pid:16663 sync_archive_users:main:132 Committed 212 users.
    INFO     2025-03-11 21:15:02.910 pid:16663 sync_archive_users:main:138 Completed syncing users. Duration: 0:00:00.308459.

.. _admin_superuser:

Admin Superuser
+++++++++++++++
An admin superuser account should be created on a fresh installation of the archive::

    $ source /opt/lick_archive/bin/activate
    $ manage.py createsuperuser
