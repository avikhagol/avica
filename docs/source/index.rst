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

AVICA: Automated VLBI pipeline in CASA.

.. asciinema:: 1016974
   :rows: 30
   :cols: 120
   :speed: 1.5
   :theme: dracula
   :autoplay: 1

.. centered:: Demo of the AVICA pipeline running end-to-end.


About
=====

**AVICA** is a Python package for the automated calibration of Very Long Baseline Interferometry (VLBI) data.
It provides modules to ingest, manipulate, and calibrate *FITS-IDI* and *Measurement Set* files containing raw visibilities.

Installation
============


> Needs Ubuntu 18.04+, Debian 10+, RHEL/CentOS 8+ \
> Python >=3.9

The `avica` package is publicly available on [PyPI](https://pypi.org/project/avica/).
Installation is recommended using [uv](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer) or [pipx](https://pipx.pypa.io/stable/how-to/install-pipx/) within a isolated environment:

using `uv`

.. code-block:: bash

    uv tool install avica --python 3.11

or using `pipx`

.. code-block:: bash

    pipx install avica


or using `pip`

.. code-block:: bash

    pip install avica

.. note:: It is recommended to use `venv` for installation, if you are not using `pipx` or `uv`.


Setup
=====

Since the pipeline's calibration features rely on `rPicard`_ please follow the linked setup instructions first.
Once **rPicard** is properly configured, you only need a minimal avica configuration file to get started.

.. _rPicard: https://bitbucket.org/M_Janssen/picard/src/master/

Configuration
=============

The pipeline is configured via a plain-text file in the current working directory, defaulting to ``avica.inp``.

.. code-block:: python

   # required
   # assumes `folder_for_fits` is a folder containing all the raw visibility fits files.
   # `casadir` is the path to the monolithic CASA installation used for running CASA tasks.

   folder_for_fits           =   /path/to/source/folder/with/raw/visibility/fitsfiles
   casadir                  =  "path/to/monolithic-casa/casa-6.x.x-xx-py3.xx.xxx/"

   # optional-1
   # `picard_input_template` is a template for the picard input file, see https://bitbucket.org/M_Janssen/picard/src/master/input_template/.
   # assumes `target_dir` is a folder where the pipeline output will be saved.
   # `accor_solint` is the number of solint partitions to use.

   target_dir                =   "reductions"
   picard_input_template     =   "path/to/rpicard"
   accor_solint              =   4
   mpi_cores_rpicard         =   10
   mpi_cores_snrating        =   5
   mpi_cores_importfitsidi   =   5
   hi_freq_ref               =   11
   snr_threshold_phref       =   7
   flux_threshold_phref      =   0.15
   min_channel_flagging      =   32
   n_calib                   =  5
   n_refant                  =  4
   minsnr                    =  3.2

   sci_solints               =   auto
   solint_max_scan_partitions=   8
   apply_flag_from_idi       =   True
   size_limit                =   2000.0

   # configure google sheet
   sheet_url                 =   None
   worksheet                 =   None

   # configure below if using CSV or google sheet to save all the result in a common sheet.
   primary_colname           =   TARGET_NAME
   primary_value             =   None
   filename_col              =   FILENAMES
   targetname_col            =   TARGET_NAME

   # optional-2 sheet configurations
   working_col               =   None
   working_col_only          =   False
   do_pcol_validation        =   False

   # experimental
   use_casadir_pythonpath    =   False
   separation_thres          =   850.0
   source_extract_multi_fitsfiles    =   False

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
