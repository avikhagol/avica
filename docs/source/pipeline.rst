Pipeline Workflow
==================

Execution
---------

Run the default pipeline:

.. code-block:: bash

   avica pipe run --target <target-name> --fitsfilenames <file1.uvfits,file2.uvfits>

Run only some steps by passing their names:

.. code-block:: bash

   avica pipe run preprocess_fitsidi fits_to_ms --fitsfilenames <file.uvfits>

The default pipeline executes these steps:

* ``preprocess_fitsidi``
* ``fits_to_ms``
* ``phaseshift``
* ``avica_avg``
* ``avicameta_ms``
* ``avica_snr``
* ``avica_fill_input``
* ``avica_split_ms``
* ``rpicard``

Common options:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Option
     - Description
   * - ``--f``, ``--fitsfilenames``
     - Comma-separated FITS-IDI file names.
   * - ``--t``, ``--target``
     - Selected field or source name.
   * - ``--configfile``
     - Configuration file containing ``key=value`` entries. Defaults to
       ``avica.inp``.
   * - ``--resume``
     - Resume after the last successful step in the result CSV.
   * - ``--resume-from``
     - Start from this pipeline step.
   * - ``--help``
     - Show the full command help.


Flowchart
---------
.. raw:: html

   <object data="_static/images/pipeline-workflow.svg" type="image/svg+xml" width="100%">
      <img src="_static/images/pipeline-workflow.svg" alt="Pipeline Flowchart" />
   </object>

    The pipeline workflow. The workflow is managed by <a href="https://github.com/avikhagol/alfrd" >ALFRD</a>.

Output layout
-------------

The output folder structure follows this convention:

::

   CWD/
   |-- avica.inp
   `-- reductions/
       `-- PROJECT_CODE/
           `-- wd/
               `-- wd_{BAND}/
                   `-- wd_{BAND}_{TARGET_NAME}/

Pre-process FITSIDI
-------------------

Sanity checks on the FITSIDI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Checks the FITSIDI file for the known problems using ``avica.fitsidiutil.fitsidi_check``.

.. list-table:: FITSIDI Known Problems & Identifiers
   :widths: 25 75
   :header-rows: 1

   * - Problem Code
     - Description
   * - primary
     - primary header check for fitsidi standards
   * - binary
     - Binary data (e.g., unexpected backslashes or encoding issues) found in string columns of the HDU table data.
   * - extra_byte
     - Extra bytes found at the end of the file (detected via ``avica.fitsidiutil.FITSIDI.check_extrabytes``).
   * - empty
     - Null or empty values found in required columns (e.g., missing Polarization types).
   * - date
     - Date format is incorrect or non-standard in headers like ``DATE-OBS`` or ``RDATE``.
   * - duplicates
     - Duplicate source entries or IDs found within the ``SOURCE`` or ``ANTENNA`` HDU tables.
   * - zeros
     - Leading zeros found in source names which can cause indexing issues in the current _CASA_ version.
   * - col_spell
     - The column names in the HDU tables such as ``FREQID`` if malformed.
   * - multifreqid
     - Multiple Frequency IDs detected when a single ID is expected.
   * - anmap
     - Incorrect antenna mapping detected in ``FLAG`` or ``PHASE-CAL`` tables.

The same checks are available on the command line:

.. code-block:: bash

   avica fitsidi_check <file.uvfits>

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Option
     - Description
   * - ``--fix``, ``--no-fix``
     - Apply available fixes. Defaults to ``--no-fix``.
   * - ``--desc``, ``--no-desc``
     - Show issue descriptions. Defaults to ``--no-desc``.
   * - ``--help``
     - Show the full command help.

Example output:

.. code-block:: text

   avica fitsidi_check VLBA_VSN005412_file3.uvfits
   +--------------------+---------+-------+-------+----------------+----------+
   | hdu                | fixable | total | fixed | problem_code   | affected |
   +==========================================================================+
   | ARRAY_GEOMETRY     | 0       | 8     | 0     | []             | []       |
   | ANTENNA            | 0       | 16    | 0     | []             | []       |
   | FREQUENCY          | 0       | 8     | 0     | []             | []       |
   | PHASE-CAL          | 0       | 12    | 0     | []             | []       |
   | PRIMARY            | 1       | 10    | 0     | ["extra_byte"] | [""]     |
   | SOURCE             | 0       | 8     | 0     | []             | []       |
   | FLAG               | 0       | 12    | 0     | []             | []       |
   | UV_DATA            | 0       | 8     | 0     | []             | []       |
   | GAIN_CURVE         | 0       | 8     | 0     | []             | []       |
   | SYSTEM_TEMPERATURE | 0       | 8     | 0     | []             | []       |
   +--------------------+---------+-------+-------+----------------+----------+

Pre-Process FITS-IDI
~~~~~~~~~~~~~~~~~~~~

  - Fixes known problems in the fits.
  - Check scanlist, print listobs if scanlist output file not found in metadata.
  - Split sources to contain only desired sources.
  - Split in frequency id and attach missing tsys, gain curve table.
  - Fill optional metadata in the calibration input files.


FITSIDI to Measurement Set
--------------------------

  - Uses the last used fitsfiled to run ``importfitsidi``.
  - Runs iteratively for files requiring different vis output.
  - Appropriate Casa task is triggered with the correct python environment using ``payload service``.
  - Logs "vis exists!" when the visiblity file is already present.

Station flag files
~~~~~~~~~~~~~~~~~~

During ``fits_to_ms``, AVICA also discovers station flag files in
``artifact_dirs``, ``folder_for_fits``, the input FITS directories, and
``<workdir>/raw``. AIPS UVFLG files using ``ANT_NAME`` (such as EVN ``.flag``
files) are converted and added after the existing FITS-IDI/MS flags.

.. code-block:: ini

   apply_flag_from_artifacts = True
   artifact_flag_extensions = .fg;.uvflag;.uvflg;.uvfg;.flag;.flg;.uvflags;.uvflgs;.uvfgs;.flags;.flgs
   artifact_flagfiles = []

Extensions are case-insensitive. A nonempty ``artifact_flagfiles`` list
overrides automatic discovery and accepts arbitrary filenames. Set
``apply_flag_from_artifacts=False`` to disable this pass independently of
``apply_flag_from_idi``. Existing measurement sets are flagged only when
``apply_flag_to_existing_vis=True``.

Supported UVFLG fields are ``ANT_NAME``, ``TIMERANG``, ``OPCODE='FLAG'``,
``REASON``, ``TIMEOFF``, ``DTIMRANG``, ``BIF``/``EIF``, and
``BCHAN``/``ECHAN``. ``TIMEOFF`` and ``DTIMRANG`` are in seconds and retain
their nonzero settings between entries, following `AIPS UVFLG INTEXT
semantics`_. Malformed files and records with unsupported selectors, invalid
IF/channel ranges, absent antennas, or unrelated times are reported and
skipped.

Generated commands are saved as ``<MS>.artifact_flags.flagcmd``; its ``.json``
sidecar records input files, row counts, skipped records and application
status. Each application saves uniquely named ``before_artifact_flags_*`` and
``after_artifact_flags_*`` versions using CASA flagmanager. If application
fails, the step reports failure and the before-version remains available for
restoration. Source flag files are read in place and are not copied into
rPICARD directories.

.. _AIPS UVFLG INTEXT semantics: https://www.aips.nrao.edu/cgi-bin/ZXHLP2.PL?UVFLG


Phaseshift
----------

  - Works if coordinate file was provided e.g `class_search_coord.ascii`.
  - Match sources by coordinate and phaseshift if not coordinates within ``1 arcsecond``.


Average Measurement Set
-----------------------

  - When required average data to ``2s`` and ``500KHz`` in time and frequency resolution.
  - Split the averaged data by removing filtered anenna.


SNR Rating
----------

  - For each band separated Measurement Set,
  - The FFT SNR is calculated for each scan and baseline, using the solution interval of scan length.
  - The SNR values are then used to rate the Sources, and antennas to select the best scans and antennas for fringe fitting.

Final Split in MS
-----------------

  - The final configuration file is used to split the data to contain only the necessary sources.

Calibration
-----------

  - The final split MS data is used for the calibration.
  - The calibration is performed using the rPicard framework.

Reading Pipeline Results
------------------------

After each step completes, AVICA appends a row to
``reductions/result__<target>__<project_code>__<workdir>.csv``, e.g.
``result__J0102+5824__EY034__wd_1.csv``. The project code and workdir identify
which working directory (``reductions/<project_code>/<workdir>/``) the results
belong to. The ``avica pipe result`` command renders that file in several
layouts.

.. code-block:: bash

   # Default: progress ladder — one row per step, with status, counts,
   # duration, and condensed failure notes
   avica pipe result --target J1234+5678

   # Suppress the full failure detail panels below the table
   avica pipe result --target J1234+5678 --no-detail

   # Compact one-liner for scripts and CI
   avica pipe result --target J1234+5678 --oneline

   # Full run history: every retry of every step
   avica pipe result --target J1234+5678 --history

   # Exit non-zero when any step has not fully succeeded
   avica pipe result --target J1234+5678 --check

   # Pick among result CSVs of the same target
   avica pipe result --target J1234+5678 --project EY034 --workdir wd_1

   # Pass the CSV path directly, skipping config lookup
   avica pipe result --csvfile reductions/result__J1234+5678__EY034__wd_1.csv

If a target has result CSVs for several workdirs, they are listed and the
newest one is shown; narrow the choice with ``--project`` / ``--workdir``, or
pass ``--csvfile``. Result CSVs from older AVICA versions
(``<target>_result.csv``) are still read when no new-style file exists.

Step Status
~~~~~~~~~~~

Each step is classified into one of four statuses:

.. list-table::
   :widths: 15 85
   :header-rows: 1

   * - Status
     - Meaning
   * - ``ok``
     - All items processed successfully (``success_count > 0``, ``failed_count == 0``)
   * - ``partial``
     - Some items succeeded and some failed — pipeline considers this step incomplete
   * - ``failed``
     - No items succeeded (``failed_count > 0``, ``success_count == 0``)
   * - ``pending``
     - Step has not been attempted yet

The result CSV is **append-only**: re-running a step appends a new row rather
than overwriting.  The default ladder view collapses to the most recent attempt
per step; ``--history`` shows all attempts.  The resume command printed in the
footer,

.. code-block:: bash

   avica pipe run --resume-from <step>

starts from the first step that has not yet achieved ``ok`` status.

Logs
----

Each ``avica pipe run`` writes its logs next to each other in the directory it
is started from:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Folder
     - Content
   * - ``avica.logs/``
     - AVICA pipeline log, crash snapshots
   * - ``casa.logs/casa__log-<YYYYmmdd_HHMMSS>.log``
     - the single CASA log of that run (all steps, all bands)
   * - ``casa.logs/err-casa__log-<YYYYmmdd_HHMMSS>.log``
     - CASA worker stderr and tracebacks of failed CASA tasks

Every CASA task is preceded by a marker line naming the step, task and
visibility, so a run can be followed on the terminal:

.. code-block:: bash

   grep -n '>>> avica' casa.logs/casa__log-*.log

A resumed run starts a new CASA log. rPICARD keeps its own logs in its working
directory.
