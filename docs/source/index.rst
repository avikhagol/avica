.. avica documentation master file, created by
   sphinx-quickstart on Thu Mar 12 15:27:27 2026.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.



.. toctree::
   :hidden:
   :maxdepth: 4
   :caption: Contents:

   pipeline
   api
   examples
   genindex

Getting Started
===============

Automated VLBI pipeline in CASA.

.. asciinema:: 945113
   :rows: 30
   :cols: 120
   :speed: 1.5
   :theme: dracula
   :autoplay: 1

.. centered:: Demo of the AVICA pipeline running end-to-end.


About
=====

**avica** is a Python package for the automated calibration of Very Long Baseline Interferometry (VLBI) data.
It provides modules to ingest, manipulate, and calibrate *FITS-IDI* and *Measurement Set* files containing raw visibilities.

Installation
============

Since the monolithic version of casa includes its own internal Python 3 installation,
it is best to install avica within a Python environment that matches the casa version.

Specifically, if you are not using the "all" installation option,
you should use the casa Python executable itself to create a virtual environment first:

.. code-block:: bash

   $ /path/to/casadir/bin/python3 -m venv MY_ENV_DIR
   $ source MY_ENV_DIR/bin/activate


.. code-block:: bash

   $ pip install avica

Alternatively, you can use the following installation method,
which automatically includes the necessary casa dependency for avica's internal operations.

.. code-block:: bash

   $ pip install avica[all]

Note that you must still provide the path to your casadir.
This ensures that the pipeline uses the same monolithic casa version, ideally the one downloaded for
rPicard to execute specific tasks like mstransform and importfitsidi within an isolated environment.

Setup
=====

Since the pipeline's calibration features rely on `rPicard`_ please follow the linked setup instructions first.
Once **rPicard** is properly configured, you only need a minimal avica configuration file to get started.

.. _rPicard: https://bitbucket.org/M_Janssen/picard/src/master/

Configuration
=============

The pipeline is configured via a plain-text file in the current working directory, defaulting to ``avica.inp``.

.. code-block:: python

   # Required
   folder_for_fits         =  "reductions/"
   target_dir              =  "/path/to/target/dir"
   casadir                 =  "path/to/monolithic-casa/casa-6.x.x-xx-py3.xx.xxx/"

   # Optional
   picard_input_template   =  "/path/to/input_template"
   mpi_cores_rpicard       =  10
   rfc_catalogfile         =  "/path/to/rfc/catalogfile"
   separation_thres        =  850.0
   size_limit              =  2000.0
   sheet_url               =  None
   worksheet               =  None
   n_calib                 =  5
   n_refant                =  4
   snr_threshold_phref     =  6
   minsnr                  =  3.2


Usage
======

The pipeline steps can be invoked from the terminal as follows:

.. code-block:: bash

   avica pipe run --t TARGET_NAME --f FITSFILE_NAME [STEPS]

The output folder structure follows the following convention:

::

   CWD (with avica.inp)
   └── reductions/
       └── PROJECT_CODE/
           └── wd/
               └── wd_{BAND}/
                   └── wd_{BAND}_{TARGET_NAME}/

using ``--help`` will print the pipeline steps and usage instructions as follows:

.. code-block:: bash

   Usage: avica pipe run [OPTIONS] [STPS]...

   _______________________

   pipeline steps:
   -   preprocess_fitsidi
   -   fits_to_ms
   -   avica_avg
   -   avicameta_ms
   -   avica_snr
   -   avica_fill_input
   -   avica_split_ms
   -   rpicard

   ________________________

   ╭─ Arguments ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
   │   stps      [STPS]...  steps for execution [default: preprocess_fitsidi, fits_to_ms, avica_avg, avicameta_ms, avica_snr, avica_fill_input, avica_split_ms, rpicard] │
   ╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
   ╭─ Options ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
   │ --f,--fitsfilenames        TEXT  fitsfile names comma separated                                                                                                     │
   │ --t,--target               TEXT  Selected field / sourc name                                                                                                        │
   │ --configfile               TEXT  config file containing key=value [default: avica.inp]                                                                              │
   │ --help                           Show this message and exit.                                                                                                        │
   ╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯



Index
==================

* :ref:`genindex`
* :ref:`search`
