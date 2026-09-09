
Pipeline Workflow
==================

Execution
---------

The pipeline steps can be invoked using the following command:

.. code-block:: bash

  avica pipe run --t TARGET_NAME --f fitsfilenames


Flowchart
---------
.. raw:: html

   <object data="_static/images/pipeline-workflow.svg" type="image/svg+xml" width="100%">
      <img src="_static/images/pipeline-workflow.svg" alt="Pipeline Flowchart" />
   </object>

    The pipeline worflow. The workflow is managed by <a href="#" >ALFRD</a>.

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

After ``avica pipe run`` completes (or is interrupted), a result CSV is written
to ``reductions/<target>_result.csv``.  The ``avica pipe result`` command
renders that file in several layouts.

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

   # Pass the CSV path directly, skipping config lookup
   avica pipe result --csvfile reductions/J1234+5678_result.csv

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
