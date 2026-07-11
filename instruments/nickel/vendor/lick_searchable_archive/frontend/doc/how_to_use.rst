Introduction to the Mt. Hamilton Data Archive & Repository
==========================================================

Since late 2006, all data acquired at Lick Observatory's Nickel telescope,
Shane telescope, and CAT are automatically placed into a data archive on a
RAID system at Mt Hamilton. Those data are automatically mirrored to another
RAID system at the UCO/Lick headquarters on the UCSC campus. Therefore the
data are reasonably safe from physical catastrophe such as fire or earthquake,
as well as simple disk failure.

Any questions about the archive may be sent to sa@ucolick.org.

Connecting to the Archive: The Archive URLs
===========================================

The archive is currently hosted at the UCSC campus at:

    https://archive.ucolick.org/


For Observers
=============

Because all observing data are promptly and automatically copied to the
campus mirror archive over the narrow link from Mt Hamilton, you do not need
to make a similar slow transfer from Mt Hamilton to your home institution.
Instead, we ask that, if possible, you wait until you are at your home
institute, and then use your web browser to fetch your data via a high-speed
connection between the UCO/Lick server at UCSC and your home institution.

We do recommend that you verify that your data are in the archive before
leaving the mountain or closing your remote observing session. It typically
takes between 1 and 16 minutes for the data appear in the Mt Hamilton archive;
the actual time depends on the particular data-taking system in use, and how
quickly the archiver system can determine that a given file is ready for transfer.


Public And Proprietary data
===========================

The archive contains both public and proprietary data.  To be able to query or
download your proprietary data you will need to login, using the login button
at the top right of the archive page.

This will navigate to the login page which will prompt for a username and
password. The account system is the same as used in the previous lick archive website.
It shares the same password but uses your e-mail address as the username.

.. image:: images/login.png
   :width: 1100 px

Public data can be accessed by anyone without logging in. By default proprietary
data becomes public after 2 years have passed.

Searching for data
==================

There are four primary fields the archive uses to query for data. At least one
must be given, however multiple fields can be queried on by checking multiple
checkboxes. The fields are:

**Object Name** This is the object name as reported in the FITS header of the
file.

.. image:: images/object_query.png
   :width: 1024 px

Use the pull down list for this field to determine how matching is
performed.

  ================== ===============================================================
   Operation          Meaning
  ================== ===============================================================
   ``=``              Object names matching the exact given value are searched for.
   ``starts with``    Object names starting with the given value are searched for.
   ``contains``       Object names  containing the given value are searched for.
  ================== ===============================================================

The "Match case" checkbox affects all of the above options. If it is checked,
matching is case sensitive, otherwise it is case insensitive. For example, the
query in the above screen shot will return files with an object name containing
``Feige 110``, but not ``feige 110`` or ``Feige110``.


**Observation date**  This is the date an observation was taken. All dates are
based on noon to noon pacific standard time.

.. image:: images/date_query.png
   :width: 1024 px


Dates should be entered in ISO-8601 YYYY-MM-DD format. Use the pull down list
to choose between selecting an individual date or a date range. Date ranges are
inclusive. All dates are in Pacific Standard Time (UTC-8). For example, the above
screenshot will return all files taken during May 2019 that you have permission for.

**Path and Filename** The path and filename within the archive.

.. image:: images/filepath_query.png
   :width: 1024 px

Each file is stored under a path based on the date the file was placed into the archive and
the instrument that was used.  Like with Object name, use
pull down list to determine how the search is performed. ``=`` and
``starts with`` operations are supported. For example: the screenshot above will find
files created by the Shane Kast instrument on the night of May 23, 2019.

**Location**  The location of an observation on the sky.  Use this to search for
all files within a given radius of a given RA and DEC.

.. image:: images/coord_query.png
   :width: 1024 px

The RA and DEC can be specified in decimal degrees or in sexagesimal . The radius defaults to
arcseconds but the units can be specified using "dms" unit specifiers. If not
given the radius defaults to 1 arcminute. For example the following values will all find the same
files:

    ====== ============== =============
    RADIUS RA             DEC
    ====== ============== =============
    60     23h 19m 58.4s  -5d 9m 56.27s
    1m     23:19:58.4     -5:9:56.27
           349.993        -5.166
    ====== ============== =============

**Instrument** Use the instrument checkboxes to filter the query results based on instrument.

.. image:: images/instruments.png
   :width: 1024 px


**Result Format** How to format the results of the query.

.. image:: images/result_format.png
    :width: 1024 px

*Count Only* To show only a count of results instead of data from the matching files,
select the "Return only a count of matching files" radio box. This will disable the
other controls in the `Result Format`` section..

*Results / Page* Change how many results are shown per page.

*RA/DEC Format* Change the format that coordinates are formatted in query results.
Available options are `sexagesimal` (i.e. degrees/minutes/seconds), `decimal degrees`,
and `as in header`.

*Sorting* Control which field to sort by, and which direction to sort in.

*Result Fields* Select which metadata fields to return in the query results.
See `Description of all fields`_ more information about what fields are available.

Finally use the ``Submit Query`` button to run the query against the archive database.

**Downloading data**

To download a single file from the archive, click on its filename. To download
multiple files, click the checkbox next to each file in the results you wish
to download. The ``Select All`` checkbox can be used to select or deselect all
of the results being displayed. Clicking the ``Download Selected`` button will
download the selected files as a tarball.  The ``Download All`` button will
download a tarball of all files returned by the query, regardless of whether
they have been selected or are on the current page.

.. _`Description of all fields`: fields.html
