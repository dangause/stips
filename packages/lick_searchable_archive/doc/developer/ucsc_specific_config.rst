
UCSC Config
===========

Hosts
-----

+-------------------------+-----------------------+
| Host                    | Role                  |
+=========================+=======================+
| ``Quarry.ucolick.org``  | Archive Software Host |
+-------------------------+-----------------------+
| ``legion.ucolick.org``  | Archive data host     |
+-------------------------+-----------------------+

Users on Quarry
---------------

+-----------+------+-----------------+--------------------------------------------+
|User       | UID  | Groups          | Purpose                                    |
+===========+======+=================+============================================+
|archive    | 1010 | archive, mhdata | Account that owns and runs the archive     |
|           |      |                 | software. Does not allow logins.           |
+-----------+------+-----------------+--------------------------------------------+
|localdusty | 1000 | archive, mhdata | Admin account used for logging in to and   |
|           |      |                 | deploying the archive. Allows login.       |
|           |      |                 | (Should probably be fixed to "dusty")      |
+-----------+------+-----------------+--------------------------------------------+
|mhadmin    | 1009 | mhdatas         | Admin account that owns the archive        |
|           |      |                 | data, made for consistency with the NFS    |
|           |      |                 | server. Does not allow logins.             |
+-----------+------+-----------------+--------------------------------------------+

Groups on Quarry
----------------

+----------+------+----------------------------------------------------------+
| Group    | GID  | Purpose                                                  |
+==========+======+==========================================================+
| archive  | 1040 | Group account for the archive software.                  |
+----------+------+----------------------------------------------------------+
| mhdata   | 1039 | Group account for the archive data, made for consistency |
|          |      | with the NFS server.                                     |
+----------+------+----------------------------------------------------------+

Database Users
--------------

+----------------+------------------------------------------------------+
| User           | Purpose                                              |
+================+======================================================+
| archive        | Creates and owns the databases on the server. Django |
|                | apps use this to access the archive_django DB.       |
+----------------+------------------------------------------------------+
| archive_query  | Used for read only access of the metadata database.  |
+----------------+------------------------------------------------------+
| archive_ingest | Used to ingest new files into the metadata database. |
+----------------+------------------------------------------------------+

.. _installation_notes:

Installation Notes
------------------

KROOT
^^^^^

``kroot/etc/Config.perhost/Quarry.ucolick.org``::

    #
    # This machine starts with the standard Lick configuration:
    #
    . Config.byclass/config.master.lick2

    #
    # This machine is a data archive host at UC Santa Cruz.
    #
    . Config.byclass/locale-none

    # Override the Keck-specified $KROOT/var group:
    RELVARGID=archive
    #
    # Use the OS-provided Tcl.
    #

    TCL_DIR=
    TK_DIR=

    TCL_DIR_CONFIG_SH=/usr/lib
    TK_DIR_CONFIG_SH=/usr/lib

``kroot/music/services/svc.byhost/Quarry.ucolick.org``::

    host:Quarry.ucolick.org
    include:%D/svc.bylocale/locale-lickShared


LROOT
^^^^^

``lroot/etc/Config.perhost/Quarry.ucolick.org``::

    #
    # This machine starts with the standard SPG configuration:
    #
    loadscript Config.byclass/config.master.lick

    # This machine is a data archive host at UC Santa Cruz.
    #
    loadscript Config.byclass/locale-ucsc


``lroot/etc/targetRules/Quarry.ucolick.org``::

    # Build anything:
    target : !*install => allow

    # Uninstall anything -- this allows us to back out of a situation
    # where we installed too much, tightened the install targetRules,
    # and would now like to uninstall the unwanted stuff.
    target : uninstall => allow

    # Install anything non-daemon:
    target : install ; branch-type : !daemon untyped => allow

    # Install schedule directory so Mt Hamilton archive SW can access scheduler info
    target : install ; branch-type : daemon ;
            repositorydir: lroot/schedule ; => allow
