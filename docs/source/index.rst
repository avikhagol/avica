.. vasco documentation master file, created by
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

VLBI and SMILE-based CASA optimizations.

About
=====

**vasco** is a Python package for the automated calibration of Very Long Baseline Interferometry (VLBI) data.
It provides modules to ingest, manipulate, and calibrate *FITS-IDI* and *Measurement Set* files containing raw visibilities.

Installation
============

.. code-block:: bash

   $ pip install vasco[all]

Setup
=====

The pipeline functionality for calibration depends on `rPicard`_. Follow the setup instructions following the link.
Once rPicard has been successfully configured, only a minimal **vasco** configuration file is required.

.. _rPicard: https://bitbucket.org/M_Janssen/picard/src/master/

Configuration
=============

The pipeline is configured via a plain-text file in the current working directory, defaulting to ``vasco.inp``.

.. code-block:: python

   # Required
   folder_for_fits         =  "reductions/"
   target_dir              =  "/path/to/target/dir"

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

   vasco pipe run --t TARGET_NAME --f FITSFILE_NAME [STEPS]

The output folder structure follows the following convention:

::

   CWD (with vasco.inp)
   └── reductions/
       └── PROJECT_CODE/
           └── wd/
               └── wd_{BAND}/
                   └── wd_{BAND}_{TARGET_NAME}/

using ``--help`` will print the pipeline steps and usage instructions as follows:

.. code-block:: bash

   Usage: vasco pipe run [OPTIONS] [STPS]...                                                                                                                                                                                                                                                                                    
                                                                                                                                                                                                                                                                                                                              
   _______________________                                                                                                                                                                                                                                                                                                      
                                                                                                                                                                                                                                                                                                                                 
   pipeline steps:                                                                                                                                                                                                                                                                                                              
   -   preprocess_fitsidi
   -   fits_to_ms
   -   vasco_avg
   -   vascometa_ms
   -   vasco_snr
   -   vasco_fill_input
   -   vasco_split_ms
   -   rpicard

   ________________________                                                                                                                                                                                                                                                                                                     

   ╭─ Arguments ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
   │   stps      [STPS]...  steps for execution [default: preprocess_fitsidi, fits_to_ms, vasco_avg, vascometa_ms, vasco_snr, vasco_fill_input, vasco_split_ms, rpicard] │
   ╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
   ╭─ Options ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
   │ --f,--fitsfilenames        TEXT  fitsfile names comma separated                                                                                                     │
   │ --t,--target               TEXT  Selected field / sourc name                                                                                                        │
   │ --configfile               TEXT  config file containing key=value [default: vasco.inp]                                                                              │
   │ --help                           Show this message and exit.                                                                                                        │
   ╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯



Index
==================

* :ref:`genindex`
* :ref:`search`