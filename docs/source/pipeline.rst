
VASCO Pipeline
=======



Flowchart
--------------
.. raw:: html

   <object data="_static/images/pipeline-workflow.svg" type="image/svg+xml" width="100%">
      <img src="_static/images/pipeline-workflow.svg" alt="Pipeline Flowchart" />
   </object>

    The pipeline worflow. The workflow is managed by <a href="#" >ALFRD</a>.

Pre-process FITSIDI
----------------

Sanity checks on the FITSIDI
~~~~~~~~~~~~

Checks the FITSIDI file for the known problems using ``vasco.fits.fitsidi_check``.

.. list-table:: FITSIDI Known Problems & Identifiers
   :widths: 25 75
   :header-rows: 1

   * - Problem Code
     - Description
   * - binary
     - Binary data (e.g., unexpected backslashes or encoding issues) found in string columns.
   * - bytesize
     - Extra bytes found at the end of the file (detected via ``fitsverify``).
   * - empty
     - Null or empty values found in required columns (e.g., missing Polarization types).
   * - date
     - Date format is incorrect or non-standard in headers like ``DATE-OBS`` or ``RDATE``.
   * - naxis
     - Incorrect ``NAXIS`` value found in the Primary Header (expected 0 for FITS-IDI).
   * - duplicates
     - Duplicate source entries or IDs found within the ``SOURCE`` table.
   * - zeros
     - Leading zeros found in source names which can cause indexing issues.
   * - spfreqid
     - The ``FREQID`` column name is malformed (e.g., contains spaces or dots).
   * - multifreqid
     - Multiple Frequency IDs detected when a single ID is expected for the calibration set.
   * - spantno
     - The Antenna Number column name is incorrect (e.g., not matching ``ANTENNA_NO``).
   * - anmap
     - Incorrect antenna mapping detected in ``FLAG`` or ``PHASE-CAL`` tables.
   * - array
     - The required ``ARRAY`` column is missing from the table.

Generate ANTAB file
~~~~~~~~~~~~

uses ```vasco.fits.antab``` to generate an ANTAB calibration file downloading the tables containing the `SYSTEM_TEMPERATURE` and `GAIN_CURVE` data from the VLBA archive.


FITSIDI to Measurement Set
----------------

Converts the FITSIDI file(s) to a Measurement Set (MS) format.


Phaseshift
----------------

If configured, checks the Measurement Set for the true source coordinates for a possible phase offset from the center, and applies a phase shift to the MS.


Average Measurement Set
----------------

The input MS is averaged in time and frequency to the specified time and frequency resolution.


SNR Rating
----------------

For each band separated Measurement Set, the FFT SNR is calculated for each scan and baseline, using the solution interval of scan length.
The SNR values are then used to rate the Sources, and antennas to select the best scans and antennas for fringe fitting.

Final Split in MS
----------------

The final configuration file is used to split the data to contain only the necessary sources.

Calibration
----------------

The final split MS data is used for the calibration.
The calibration is performed using the rPicard framework.