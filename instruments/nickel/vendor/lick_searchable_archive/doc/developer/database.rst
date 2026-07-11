********
Database
********
The Archive PostgresSQL cluster is named ``archive_db``. It currently has two databases ``archive``
and ``archive_django``. The ``archive`` user owns both. At least the naming convention is consistent.

Tables
======
TBD maybe automagically generate some of this documentation from the SQLAlchemy code so it stays up to date?

``main``
--------
Currently most of the data in the archive is stored in the ``main`` table. It has columns for
each item in the Lick Searchable Archive Metadata Schema (TBD link). This design was chosen for query performance,
as it eliminates joins. However if it becomes too cumbersome it may be split in the future. The
additional columns not in the Metadata Schema are:


``id``
    An integer sequential id for the table, and also the primary key.

``header``
    A large text field with the entire FITS header as extracted with Astropy. Intended to be
    used when adding or updating metadata fields without having to re-read every file in the archive.
    Clients will also be able to request the header for a file using the Query API.

``coord``
    A pgsphere Spoint with the ra/dec. This is indexed allowing for fast searches wiht sky coordinates.

Indexes
^^^^^^^
* ``obs_date``
* ``instrument``
* ``object``
* ``frame_type``
* ``coord``

Constraints
^^^^^^^^^^^
* Unique constraint on ``filename`` to prevent duplicates in the archive database.


.. _db_admin:

Administration
==============

Database Filesystem
-------------------
On Quarry there is a separate 200GiB partition for database storage, mounted under `/pg_data`.

``pg_data/archive_db``
    The database storage itself.

``pg_data/backups``
    Automatic backups of the database are stored here. Only up to 7 days of backups are kept.

``pg_data/saved_backups``
    Used by administrators to save backups for future use.

Database Backup Cron Job
-------------------------
During ansible deployment, a cronjob for the ``postgres`` user is used to backup the database everyday at noon::

  #Ansible: Archive DB pg_dump backup
  0 8 * * * /var/lib/postgresql/scripts/archive_db_backup.sh

Admin Procedures
----------------

Querying the database
^^^^^^^^^^^^^^^^^^^^^
An admin user can use the ``psql`` program to query the database directly::

    $ psql -U archive
    archive=> select object, frame_type from main where obs_date between '2019-05-30' and '2019-05-31';

Or::

    $ echo "select * from main where coord @ scircle '< (159.9030737856363d, 43.1025582646240d), 0d2m >';" | psql -U archive -f - > output.txt

.. _db_setup:

Setup new database
^^^^^^^^^^^^^^^^^^
Ansible will install a PostgreSQL, create a database cluster, a database, and a database user
but will not create the database scheme in case the admin wants to restore from an existing backup.
To create the tables, indexes, etc for a blank new database run the following as an admin user::

   $ source /opt/lick_archive/bin/activate # if not in python virtualenv
   $ create_schema.py --read_only_user archive_query --read_write_user archive_ingest archive archive


Restore database
^^^^^^^^^^^^^^^^
To restore the database from a ``pg_dump`` backup::

    $ gunzip -c archive_db_20220505_1500.dump.gz | psql -U archive -f - -v ON_ERROR_STOP=1


Manual Backup
^^^^^^^^^^^^^
The below command backs up the database in a way that makes it easy to restore on a different
database::

    postgres@Quarry:~$ pg_dump  -U postgres archive --no-owner --no-comments | gzip > backup.dump.gz

Notice this **must be done as the postgres user**.


Upgrading database to a new schema
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Login as the postgres user, and backup the database::

       $ sudo su - postgres
       $ /var/lib/postgresql/scripts/archive_db_backup.sh

   This backup can be used to rollback if needed.

2. Create a second backup of the tables that need migrating only::

       $ cd /pg_data/saved_backups
       $ pg_dump  -U postgres archive --no-owner --no-comments --table main --data-only | gzip > archive_db_YYYYMMDD_description.dump.gz

3. Once you're sure it's a good backup, login as an archive admin user, delete the current table::

    $ psql -U archive
    psql (14.9 (Ubuntu 14.9-0ubuntu0.22.04.1))
    Type "help" for help.

    archive=> drop table main;
    DROP TABLE
    archive=> exit

4. Setup the new database schema as in :ref:`db_setup`.

5. As the postgres user, restore the database ``main`` table backup::

    $ cd /pg_data/saved_backups
    $ gunzip -c archive_db_YYYYMMDD_description.dump.gz | psql -U archive -f - -v ON_ERROR_STOP=1

The resulting data will take on any new defaults in the new schema.
