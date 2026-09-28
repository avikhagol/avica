FITS-IDI utilities
==================

Reading, inspecting, validating, splitting, and updating FITS-IDI files.

Public interface
----------------

.. autosummary::

   avica.fitsidiutil.io.FITSIDI
   avica.fitsidiutil.io.read_idi
   avica.fitsidiutil.obs.ObservationSummary
   avica.fitsidiutil.split.SplitData
   avica.fitsidiutil.validation.FITSIDIValidator
   avica.fitsidiutil.validation.fitsidi_check
   avica.fitsidiutil.op.ANTAB
   avica.fitsidiutil.op.get_dateobs
   avica.fitsidiutil.op.parse_antab
   avica.fitsidiutil.validation.fitsidi_check

Calibration tables and ANTAB bands
----------------------------------

.. automodule:: avica.fitsidiutil.calibration

.. automodule:: avica.fitsidiutil.antab_bands
