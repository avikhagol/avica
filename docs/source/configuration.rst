Configuration
=============

.. contents:: On this page
   :local:
   :depth: 1

The pipeline configuration is a plain-text ``key=value`` file. By default,
AVICA looks for ``avica.inp`` in the current working directory. The
`example configuration`_ is a good starting point.

Pass a custom configuration file with ``--configfile``:

.. code-block:: bash

   avica pipe run --configfile <path/to/config/file>

.. asciinema:: mBmNuDbzI1S2dpqN
    :rows: 30
    :cols: 133
    :speed: 1
    :theme: dracula
    :autoplay: 0

.. _example configuration: https://github.com/avikhagol/avica/blob/main/src/avica/pipe/avica_example.inp

Minimal configuration
---------------------

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
   fits_to_ms.mpi_cores      =   5
   avica_avg.mpi_cores       =   5
   avica_snr.mpi_cores       =   5
   avica_split_ms.mpi_cores  =   10
   rpicard.mpi_cores         =   10
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

Saving defaults
---------------

To store defaults persistently, merge an existing configuration file into
``~/.avica/avica.inp``:

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

Each of these commands only touches one file: ``--default`` writes to
``~/.avica/avica.inp``, ``--global`` writes to the installed ``avica.inp``, and
plain ``avica pipe config`` writes to the local ``avica.inp`` (or
``--outfile``). Only the keys you give it are changed; everything else already
in that file -- other settings, comments, ``# str``/``# int`` notes -- stays as
it was. A backup of the old file is saved as ``avica.inp.bak``.

Parameter summary
-----------------

Use ``--summary`` to print a report of every pipeline parameter, its resolved
value, and where that value came from (``global``, ``user``, ``inpfile``,
``cli``, built-in ``default``, or runtime ``context``). The ``/core`` and
``/step`` suffixes distinguish general parameters from step-specific
overrides:

.. code-block:: bash

   avica pipe config --summary --inpfile <path/to/avica.inp>

The summary overlays the installed global ``avica.inp``, then
``~/.avica/avica.inp``, then the local ``avica.inp`` (or an explicit
``--inpfile``), with command-line ``key=value`` overrides applied last. Later
layers override matching keys and preserve other settings. ``--no-inpfile``
skips automatic local-file discovery; an explicit ``--inpfile`` is still used.
Summaries do not write configuration files.

rPICARD input templates
-----------------------

To supersede the rPICARD ``input_template`` files (``array.inp``,
``observation.inp``, ``array_finetune.inp``, ``flagging.inp``,
``constants.inp``) used by the ``rpicard`` step, point
``picard_input_template_update`` at a folder containing the parameters you
want to fix:

.. code-block:: text

   picard_input_template_update   =   "path/to/folder/with/fixed/inp/files"

Cleaning up intermediate data
-----------------------------

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
