.. _access_rules:

Access Rules for Propreitary Data
=================================
:subscript:`(Taken from the original archive's Rules.txt)`

Implementation
--------------

The access for each file is determined when its metadata is ingested and then stored
in the database.

Whether a file is public or not is determined by the ``file_metadata.public_date``
field in the metadata database.

If a file is not public, which users can access it are determined by the below
access rules and then stored in the database ``user_data_access`` table.
See :ref:`Maintenance <view_user_access>` for how to view this information.

It may also be useful to view the code that applies the access rules. The
`user_access.py <https://github.com/UCObservatories/lick_searchable_archive/blob/main/lick_archive/authorization/user_access.py>`_
file implements this logic.


Access Rules Summary, in Order of Precedence
--------------------------------------------

 *  If the proprietary period for a program has expired, its data is public.
    Some instruments' data is always public (e.g. allsky cameras).

 *  If the data directory contains a file ``override.access``, that file says
    who can access certain files.  Example: you can re-assign ownership for
    a few FITS files that were acquired as part of a target-of-opportunity.

 *  If a FITS file is identified as a calibration file, access is granted
    to all observers for that telescope/calnight.

 *  If the <telescope>schedule service has an OWNRHINT for the mtime of the
    file, the schedule service database is used to return an owner for that file.

 *  If a single observer has been set in the <telescope>schedule service,
    since noon on that calnight, that observer is granted access.

 *  Otherwise access is granted to everyone in the schedule for the night.

 *  If no observers could be found for the file, it is made public.

Access Rules, Full Details
--------------------------

  We start with a file in a directory YYYY-MM/DD/<instrument>/.
  In the following, the word 'calnight' (calendar night) means YYYY-MM-DD.
  Every instrument is associated with a particular telescope, which is
  normally the telescope nickname from the telescope table, e.g. 'Shane'.
  In some cases, the name is a pseudo-telescope, such as 'Allsky' or
  'Webcam', and might not appear in the telescope table.
  The mapping from instrument to telescope is set in the telemap.cfg file
  (/usr/local/lick/data/web_archive/telemap.cfg).



0.  In all cases below, once the observer(s) are identified,
    we check if the proprietary period has expired for at least
    one observers' run for that night, and if so, the access
    becomes "public".

    If any error occurrs determining the calnight or
    the observers for a file, the access becomes "unknown".


1.  If the data directory has a file named ``override.access``, this will
    propagate to the archive directory along with the regular data files.
    after observing is complete. If it is a directory from the past week,
    the ``ingest_watchdog`` service should pick up the change automatically.
    Otherwise See :ref:`Resync Authorization <resync_auth>` for how to
    manually re-apply the access rules.

    NOTE: when you create or edit the override.access file in a data directory,
    you should modify its permissions as follows, to ensure that the
    archiver promptly responds to it, and doesn't ignore edits to it::

        chmod u+s,o-t  override.access

    The override.access rules use a <globpat> to match files, using ``*`` and ``?``
    in the way a shell does. This pattern should not contain a directory.
    Furthermore, if the globpat is like aaa.xxx, where aaa does not
    contain "." and does not end in "*", we act as if the glob pat
    is aaa{,.*}xxx, hence matches aaa.nnn.xxx and aaa.xxx.

    Example 1::

        globpat b1024.fits expands to b1024.fits and b1024.*.fits.

    Example 2::

        globpat b102*.fits is not changed.

    The override.access rules are applied as follows.

    1a. If the file contains a line matching::

        <globpat> obstype <type>

    where 'obstype' is literal, and
    the <type> is one of 'cal', 'focus', or 'flat', access is granted
    for all files matching <globpat> to all scheduled observers for
    that telescope/calnight.

    1b. If the file contains a line matching::

        <globpat> access <name> ...

    where 'access' is literal, then access to files matching
    <globpat> is granted to each name as follows:

    1bi.  If the name matches, case-insensitive, a unique
        <givenname>.<familyname> or <giveninitial>.<familyname>
        or <familyname> in the observers table for that night.
        (That is, the name doesn't have to be unique among all observers
        in the complete observers table, so long as the name is unique
        for that night.)
        We generalize this by saying that the name will be used as an
        'ownrhint' for a histsched lookup.

    1bii.  If the the name is a unique match to an entry in the observers
        table, without regard to night.

    1d. In 1b, the special name "all-observers" stands
        for all scheduled observers for that telescope/calnight.

    1e. Otherwise, if there is no unique match, the access is set to 'unknown'.

    1f. Note: if several entries match a single file, the first match wins.

    1x. If a call to histsched returns an error, access is set to 'unknown'.

    1z. If there's an error accessing the override access information in the database, access is set to 'unknown'.


2.  Otherwise, some files are "always-public", except as set
    in override.access, above:

    2a.  On a per-instrument basis, certain suffixes are always public
         access.  For example, {jpg, jpeg, mpg, mp4}, may be public access.
         The current list of public suffixes is defined in :ref:`archive_config.ini <archive_config>`
         in the ``[Public Suffixes]`` section.

    2b. Some instruments are always public access or are only owned by a single user.
        The current list of these instruments is defined in :ref:`archive_config.ini <archive_config>`
        in the ``[Fixed Owners]`` section, with ``Public.Observer`` indicating a public access
        instrument.


3. Otherwise, if the file is identified as having a ``frame_type`` of
   ``dark``, ``flat``, ``bias``, ``arc``, ``calibration``, or ``focus``
   access is granted to all observers for that telescope/calnight;
   the list of observers is found by querying the scheduling database.

   3x. If a call to histsched returns an error, access is set to 'unknown'.

4. Otherwise, OWNRHINT's, OWNRNAME's, and COVERID's are applied as follows.
    (Reminder: a data-taking application can set the keyword
    <telescope>schedule.OWNRHINT at any time.  If there are multiple
    observers in a night, it is recommended that the OWNRHINT is
    set just before the start of each image acquisition, so that
    it is correct throughout the DATE-BEG .. DATE-END period.
    Note that these are *not* collected from the FITS header;
    OWNRHINT, OWNRNAME, and COVERID come from the schedule service.)

    4a. If the file is FITS, and there are DATE-BEG and DATE-END keys, and
        the <telescope>schedule KTL service provides a unique COVERID
        value between those times:
        the hint plus the calnight and telescope name are passed to the
        histsched program for identification, and access is granted to
        the OWNRNAME and COVERID.

    4b. Otherwise, if the <telescope>schedule service provides an OWNRHINT
        value for the mtime of the file, regardless of whether it is FITS:
        the hint plus the calnight and telescope name are used to query the
        scheduling database, and access is granted to
        the resulting OWNRNAME and COVERID.

    4w. If there are multiple OWNRHINT values between DATE-BEG and DATE-END
        times, access is set to 'unknown'.

    4x. If the database query exits with an error code, access is set to 'unknown'.

    4y. If query doesn't find a valid owner to match the OWNRHINT,
        access is set to 'unknown'.

    4z. If an error occurs reading the OWNRHINT value from the keyword history
        database, access is set to 'unknown', or if DATE-BEG or DATE-END is
        not interpretable, set access to 'unknown'.

5. Otherwise if there is just one observer set in the <telescope>schedule
    service, since noon on that calnight, that observer is granted
    access.

    5q. If there are multiple scheduled observers, no access is granted.

    5x. If a call to scheduling database returns an error, access is set to 'unknown'.

6.  Otherwise there are no scheduled observers, and access is public.
