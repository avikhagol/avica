ANTAB calibration files
=======================

ANTAB is the AIPS text format for amplitude-calibration information used by
VLBI observations.  An ANTAB file can contain antenna gain curves, system or
antenna temperatures, and baseline-dependent amplitude corrections.  AIPS
writes these data to GC, TY, and BL tables; ``APCAL`` can then create an SN
table, which is normally applied with ``CLCAL``.

This page summarizes the
:download:`AIPS ANTAB help for 31DEC26
<../_static/html/AIPS_HELP_file_version31DEC26_for_ANTAB.html>`.
For official documentation, see the `AIPS ANTAB help page <https://www.aips.nrao.edu/cgi-bin/ZXHLP2.PL?ANTAB>`_.

.. warning::

   Do not blindly use VLBA ``*cal.vlba`` files dated between 2014-01-31 and
   2015-10-19 for RDBE/MARK5C observations.  Those files describe the legacy
   signal path, which differs substantially from the RDBE/MARK5C path.

General file syntax
-------------------

The format is free-form and recognizes five group keywords:

``CONTROL``
   Sets the default column mapping for subsequent ``TSYS`` and ``TANT``
   groups.

``BASELINE``
   Supplies baseline-dependent amplitude factors.

``GAIN``
   Supplies antenna gain curves and DPFU values.

``TSYS``
   Supplies system-temperature measurements.

``TANT``
   Supplies antenna-temperature measurements.

Each group may span multiple lines and must end with ``/``.  At least one
space must separate the slash from the preceding value.  Lines may contain
at most 2560 characters.  Text following ``!`` is a comment.  Arithmetic
expressions in parentheses are evaluated; for example,
``DPFU = (0.25*1.9)``.

ANTAB may update the same TY, GC, or BL table version more than once.  Newer
entries replace older matching entries, and records for a given antenna are
consolidated across IF and polarization at the end of each run.  Time ranges
that do not occur in the data's NX table are ignored.

Column mapping with INDEX and INDEX2
------------------------------------

``INDEX`` maps each value column in a ``TSYS`` or ``TANT`` record to one or
more IF/polarization pairs.  ``INDEX2`` has the same syntax and adds further
mappings for the corresponding columns.  Every value column must have an
``INDEX`` entry.  Each entry is limited to eight characters and must produce
a unique mapping.

The supported forms are:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Form
     - Meaning
   * - ``'R3'``
     - IF 3, RCP.
   * - ``'L1'``
     - IF 1, LCP.
   * - ``'R4|L4'``
     - IF 4, both RCP and LCP.
   * - ``'R1:8'``
     - IFs 1 through 8, RCP.
   * - ``'L10:16:2'``
     - Even-numbered IFs from 10 through 16, LCP.
   * - ``'X'``
     - Do not map this column.

For example, given seven measurement columns::

   321 20:02.07  33.5 36.7 34.2 32.1 38.9 39.7 23.7

the following mapping assigns column 1 to odd IFs 1--8 in both
polarizations, column 2 to IF 3 in both polarizations, and column 6 to IF 7
LCP::

   INDEX  = 'R1:8:2', 'R3', 'X', 'X', 'X',  'X', 'X'
   INDEX2 = 'L1:8:2', 'L3', 'X', 'X', 'X', 'L7', 'X'

CONTROL group
-------------

``CONTROL`` is optional, but when present it must be the first group in the
file.  It accepts only ``INDEX`` and, optionally, ``INDEX2``.  The mapping is
used by every antenna whose ``TSYS`` or ``TANT`` group does not provide its
own mapping::

   CONTROL
      INDEX = 'R1', 'L1', 'R2', 'L2', 'R3', 'L3' /

Without ``CONTROL``, ANTAB assumes one column per available IF and
polarization, ordered ``R1, L1, R2, L2, ...`` for dual-polarization data or
``R1, R2, ...`` for single-polarization data.

BASELINE group
--------------

``BASELINE`` writes an amplitude multiplier directly to the BL table.  Use
station names exactly as they appear in the AN table::

   BASELINE SC MK B = 1.9 /

This multiplies all data on the St. Croix--Mauna Kea baseline by 1.9.  More
than one ``BASELINE`` group may be present.  Each factor applies to all
sources, IFs, and polarizations on its baseline.

GAIN group
----------

Every ``GAIN`` group requires:

* an antenna name from the AN table;
* ``DPFU``, the zenith point-source sensitivity in K/Jy; and
* one gain-curve type: ``EQUAT``, ``ALTAZ``, ``ELEV``, or ``GCNRAO``.

``DPFU = X`` specifies one polarization-independent value.  For
dual-circular-polarization data, ``DPFU = X,Y`` assigns X to RCP and Y to
LCP.  Alternatively, separate ``GAIN`` groups may use the ``RCP`` or ``LCP``
keyword.

The curve types are:

``EQUAT``
   A function of hour angle in degrees.

``ALTAZ``
   A function of zenith angle in degrees.

``ELEV``
   A function of elevation in degrees.

``GCNRAO``
   A two-dimensional spherical-harmonic expansion in hour angle and
   ``90 degrees - declination``, as used by the Green Bank 140-foot antenna.

If no curve coefficients or table are supplied, the relative gain is assumed
to be flat.  ``EQUAT``, ``ALTAZ``, and ``ELEV`` curves accept one of:

``TABLE``
   Tabulated ordinate/relative-gain pairs immediately following the group.

``POLY = a0, a1, a2, ...``
   Polynomial coefficients in increasing order.  ``OFFSET = x`` may be used
   only with ``POLY`` to shift the ordinate.

``EQUAT`` may also specify ``DEC = x``.  Multiple entries with different
declinations form a two-dimensional curve for an equatorially mounted
antenna.

For ``GCNRAO``, the supported coefficient keywords are:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Keyword
     - Term
   * - ``A00``
     - 1
   * - ``A10``
     - ``cos(90-dec)``
   * - ``A11E``
     - ``sin(90-dec) cos(ha)``
   * - ``A11O``
     - ``sin(90-dec) sin(ha)``
   * - ``A20``
     - ``0.5 (3 cos^2(90-dec) - 1)``
   * - ``A21E``
     - ``3 sin(90-dec) cos(90-dec) cos(ha)``
   * - ``A21O``
     - ``3 sin(90-dec) cos(90-dec) sin(ha)``
   * - ``A22E``
     - ``3 sin^2(90-dec) cos(2 ha)``
   * - ``A22O``
     - ``3 sin^2(90-dec) sin(2 ha)``
   * - ``A30``
     - ``2.5 cos^3(90-dec) - 1.5 cos(90-dec)``

All curve types may use ``FREQ = f1, f2`` to give their valid sky-frequency
range in MHz.  ANTAB determines the corresponding IFs and FQ IDs.

A tabulated St. Croix RCP elevation curve valid from 4 to 6 GHz is written
as::

   GAIN SC ELEV DPFU = 0.13 RCP FREQ = 4000,6000 TABLE /
   10.0 0.56
   20.0 0.78
   70.0 0.94
   80.0 0.95 /

A flat gain curve for all Mauna Kea IFs and polarizations is::

   GAIN MK ALTAZ DPFU = 0.1 POLY = 1.0 /

TSYS and TANT groups
--------------------

``TSYS`` and ``TANT`` identify an antenna followed by temperature
measurements.  They accept:

``FT``
   Multiplier applied to every value; defaults to 1.0.

``TIMEOFF``
   Time offset added to every entry; defaults to zero.

``SRC/SYS``
   Indicates that the listed values are actually ``Ta/Tsys`` (VLA format).

``RANGE = low,high``
   Permitted measurement range.

``INDEX`` and ``INDEX2``
   Per-antenna column mappings, as described above.

Timestamps may use decimal hours, sexagesimal hours with decimal minutes, or
sexagesimal hours with decimal seconds::

   Day_no  hh.hh        col1 col2 ...
   Day_no  hh:mm.mm     col1 col2 ...
   Day_no  hh:mm:ss.ss  col1 col2 ...

For example::

   TSYS SC FT = 1.05 INDEX = 'R1:8', 'L1:8' /
   321 20:32.78  32.6 33.4 ! RCP, LCP
   321 20:34:01  31.6 35.8

``TANT`` has the same format as ``TSYS``.  Because antenna temperatures may
be measured across a wider bandwidth, map them to all applicable IFs with
``INDEX`` and ``INDEX2``.  Negative values and ``999.9`` are treated as
undefined.  Invalid timestamps are errors.

Running AIPS ANTAB
------------------

The input UV data must be an AIPS multi-source file with an NX table.  Run
ANTAB once for each subarray and, where applicable, before ``USUBA`` so that
the correct subarray is attached to each TY and GC record.

The principal AIPS adverbs are:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Adverb
     - Purpose
   * - ``INNAME``, ``INCLASS``, ``INSEQ``, ``INDISK``
     - Select the input UV data set.
   * - ``CALIN``
     - Select the calibration text file, for example ``FITS:ANTAB.CAL``.
   * - ``SUBARRAY``
     - Select the subarray; zero means subarray 1.
   * - ``TYVER``, ``GCVER``, ``BLVER``
     - Select the output table versions; zero means the highest version.
   * - ``SPARM``
     - List station names in the calibration file that ANTAB should ignore.
   * - ``PRTLEV``
     - A positive value echoes input lines to aid format-error diagnosis.
   * - ``OFFSET``
     - Extend both sides of each scan by this many minutes when matching
       off-scan measurements.  Leave it zero for VLBA and VLA data.

If a calibration file includes an antenna absent from the data, ANTAB can
report ``UNKNOWN PARAMETER`` while reading the KEYIN file.  First run with an
empty ``SPARM`` to identify the offending records, then add only the station
names that should intentionally be skipped.

When ``FITLD`` splits an observation into data sets with incompatible modes,
such as different IF or polarization counts, split the calibration file by
mode as well and process each file separately with ``VLOG`` before ANTAB.
