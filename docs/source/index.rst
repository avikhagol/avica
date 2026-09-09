AVICA: Automated VLBI pipeline in CASA
======================================

**AVICA** is a Python package for automated calibration of Very Long Baseline
Interferometry (VLBI) data in CASA. It provides tools to ingest, manipulate,
and calibrate *FITS-IDI* and *Measurement Set* files containing raw
visibilities.


.. contents:: On this page
   :local:
   :depth: 2

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

   pipeline
   api
   examples
   misc

Installation
------------

Requirements:

* Ubuntu 18.04+, Debian 10+, or RHEL/CentOS 8+
* Python >= 3.9

The ``avica`` package is available on `PyPI`_. Use `uv`_ or `pipx`_ for an
isolated command-line installation, or run the full installation script below
to also set up CASA and rPICARD.

Full installation script, run as your normal user. The quickest way is to
fetch and run it in one step:

.. code-block:: bash

   curl -LsSf https://avikhagol.github.io/avica/install.sh | bash
   source "$HOME/.local/share/avica-stack/env.sh"

Alternatively, download it first so you can read it before running anything:

.. code-block:: bash

   curl -fsSL https://raw.githubusercontent.com/avikhagol/avica/main/install.sh -o install.sh
   bash install.sh
   source "$HOME/.local/share/avica-stack/env.sh"

The script installs AVICA using ``uv``. If ``picard`` is already on ``PATH``,
it reuses that installation and skips all CASA/rPICARD downloads and
plotting/data setup. Otherwise, it installs rPICARD, jiveplot, and CASA
reference data.

For a new rPICARD installation, set ``CASA_PATH`` to an existing CASA
installation directory (containing ``bin/casa`` and ``bin/mpicasa``) or an
archive URL. With the one-liner, place the variable after the pipe so it
reaches ``bash``, not ``curl``:

.. code-block:: bash

   curl -LsSf https://avikhagol.github.io/avica/install.sh | CASA_PATH=/path/to/casa bash

If unset, the script prompts for a CASA location, or downloads a default
archive when run without a terminal. See ``bash install.sh --help`` (or
``curl -LsSf https://avikhagol.github.io/avica/install.sh | bash -s -- --help``
for the one-liner) for the full list of environment variables, including
``AVICA_INSTALL_DIR`` and ``PICARD_REF``.

Using ``uv``:

.. code-block:: bash

   uv tool install avica --python 3.10

Using ``pipx``:

.. code-block:: bash

   pipx install avica

Using ``pip``:

.. code-block:: bash

   pip install avica

.. note::

   If you install with ``pip``, use a virtual environment unless you already
   manage Python packages another way.

.. _PyPI: https://pypi.org/project/avica/
.. _uv: https://docs.astral.sh/uv/getting-started/installation/#standalone-installer
.. _pipx: https://pipx.pypa.io/stable/how-to/install-pipx/

Setup
-----

The pipeline calibration steps rely on `rPicard`_. Follow the rPicard setup
instructions first. After rPicard is configured, AVICA only needs a minimal
configuration file to get started.

.. _rPicard: https://bitbucket.org/M_Janssen/picard/src/master/

Configuration
-------------

The pipeline configuration is a plain-text ``key=value`` file. By default,
AVICA looks for ``avica.inp`` in the current working directory.

Pass a custom configuration file with ``--configfile``:

.. code-block:: bash

   avica pipe run --configfile <path/to/config/file>

Minimal configuration:

.. code-block:: text

   # required
   # folder_for_fits is a folder containing the raw visibility FITS files.
   # casadir is the path to the monolithic CASA installation used for CASA tasks.

   folder_for_fits           =   /path/to/source/folder/with/raw/visibility/fitsfiles
   casadir                   =   "path/to/monolithic-casa/casa-6.x.x-xx-py3.xx.xxx/"

   # optional-1
   # picard_input_template the folder containing the rPicard input file.
   # target_dir is where pipeline output will be saved.
   # accor_solint is the solution interval in seconds for the CASA accor task.

   target_dir                =   "reductions"
   picard_input_template     =   "path/to/rpicard"
   picard_input_template_update  =   ""    # optional: folder with fixed rpicard inp files to supersede defaults
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

   apply_flag_from_idi       =   True
   size_limit                =   2000.0

   # EXPERIMENTAL -------------------------
   # configure google sheet
   sheet_url                 =   None
   worksheet                 =   None

   # configure below if using CSV or google sheet to save all the result in a common sheet.
   primary_colname           =   TARGET_NAME
   primary_value             =   None
   filename_col              =   FILENAMES
   targetname_col            =   TARGET_NAME

   # sheet configurations
   working_col               =   None
   working_col_only          =   False
   do_pcol_validation        =   False

   sci_solints               =   manual
   solint_max_scan_partitions=   8
   use_casadir_pythonpath    =   False
   separation_thres          =   850.0
   source_extract_multi_fitsfiles    =   False

To store defaults persistently in ``~/.avica/avica.inp``, pass an existing
configuration file:

.. code-block:: bash

   avica pipe config --default --inpfile <path/to/avica.inp>

You can also set default values directly:

.. code-block:: bash

   avica pipe config --default key=value key2=value2 key3=value3

To set global defaults in AVICA's installed directory, use ``--global`` in the
same way:

.. code-block:: bash

   avica pipe config --global --inpfile <path/to/avica.inp>
   avica pipe config --global key=value key2=value2 key3=value3

Parameter summary
~~~~~~~~~~~~~~~~~

Use ``--summary`` to print a report of every pipeline parameter, its resolved
value, and where that value came from (``inpfile``, ``default``, ``context``,
or a per-step override):

.. code-block:: bash

   avica pipe config --summary --inpfile <path/to/avica.inp>

.. asciinema:: mBmNuDbzI1S2dpqN
    :rows: 30
    :cols: 133
    :speed: 1
    :theme: dracula
    :autoplay: 0

If ``--inpfile`` is omitted and ``avica.inp`` exists in the current directory,
it is read automatically. Combine ``--summary`` with ``key=value`` overrides
on the command line to preview how they would change the resolved
configuration before writing it out.

Cleaning up intermediate data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each pipeline step can remove its own intermediate files (temporary files,
superseded Measurement Sets, etc.) once it finishes.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Option
     - Description
   * - ``delete_removables``
     - Master switch; must be ``True`` for any cleanup to happen. Defaults to
       ``False``.
   * - ``removables``
     - List of glob patterns (relative to the step's working directory) to
       delete. Can be set globally or per step as ``<step_name>.removables``.
   * - ``rm_pre`` / ``<step_name>.rm_pre``
     - If ``True``, delete the matching files before the step runs instead of
       after.
   * - ``rm_only``
     - Only perform the deletion and skip running the step itself.

Several steps ship with sensible defaults, e.g.:

.. code-block:: text

   delete_removables               =   True
   preprocess_fitsidi.removables   =   ["raw/*.tmp"]
   rpicard.removables              =   ["wd_[SLKQXPD]/VLBI_*.ms"]
   fits_to_ms.removables           =   ["*.old"]

Deletion is always confined to the step's working directory; patterns that
resolve outside it are ignored.

Usage
-----

Run the default pipeline from the terminal:

.. code-block:: bash

   avica pipe run --target <target-name> --fitsfilenames <file1.uvfits,file2.uvfits>

Run selected steps by passing step names:

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
   * - ``--help``
     - Show the full command help.

Output Layout
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

More Documentation
------------------

See the dedicated pages for deeper usage notes and API reference:

* :doc:`pipeline`
* :doc:`examples`
* :doc:`api`
* :doc:`misc`
* :ref:`genindex`
* :ref:`search`
