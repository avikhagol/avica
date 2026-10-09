AVICA: Automated VLBI pipeline in CASA
======================================

**AVICA** is a Python package for automated calibration of Very Long Baseline
Interferometry (VLBI) data in CASA. It provides tools to ingest, manipulate,
and calibrate *FITS-IDI* and *Measurement Set* files containing raw
visibilities.

.. asciinema:: 1016974
   :rows: 30
   :cols: 120
   :speed: 4.5
   :theme: dracula
   :autoplay: 0

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Contents:

   installation
   configuration
   pipeline
   examples
   api
   misc

Quick start
-----------

Install AVICA:

.. code-block:: bash

   uv tool install avica --python 3.10

The calibration steps use `rPICARD`_ and CASA. To install AVICA, CASA and
rPICARD together, use the installation script described in
:doc:`installation`.

Create an ``avica.inp`` next to your data with at least:

.. code-block:: text

   folder_for_fits   =   /path/to/folder/with/fitsfiles
   casadir           =   "path/to/monolithic-casa/casa-6.x.x-xx-py3.xx.xxx/"

Then run the pipeline and check how it went:

.. code-block:: bash

   avica pipe run --target <target-name> --fitsfilenames <file1.uvfits,file2.uvfits>
   avica pipe result --target <target-name>

.. _rPICARD: https://bitbucket.org/M_Janssen/picard/src/master/

Where to go next
----------------

* :doc:`installation` -- PyPI, source, and the full CASA + rPICARD installer
* :doc:`configuration` -- ``avica.inp``, saved defaults, parameter summary, cleanup
* :doc:`pipeline` -- what each step does, station flag files, results and logs
* :doc:`examples` -- example output of ``avica pipe run`` and ``avica listobs``
* :doc:`api` -- Python API reference
* :doc:`misc` -- tools outside the main workflow
* :ref:`genindex`
* :ref:`search`
