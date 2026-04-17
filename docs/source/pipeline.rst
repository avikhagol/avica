
Pipeline Workflow
==============

Execution
---------

The pipeline steps can be invoked using the following command:

.. code-block:: bash

  vasco pipe run --t TARGET_NAME --f fitsfilenames


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

Checks the FITSIDI file for the known problems using ``vasco.fitsidiutil.fitsidi_check``.

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
     - Extra bytes found at the end of the file (detected via ``vasco.fitsidiutil.FITSIDI.check_extrabytes``).
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