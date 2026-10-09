Installation
============

.. contents:: On this page
   :local:
   :depth: 1

Requirements
------------

* Linux: Ubuntu 18.04+, Debian 10+, or RHEL/CentOS 8+
* Python >= 3.10
* `rPICARD`_ and a monolithic CASA build for the calibration steps (the
  installation script below can set both up for you)

.. _rPICARD: https://bitbucket.org/M_Janssen/picard/src/master/

Install the package
-------------------

The ``avica`` package is available on `PyPI`_. Use `uv`_ or `pipx`_ for an
isolated command-line installation.

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
.. _pipx: https://pipx.pypa.io/stable/how-to/install-pipx.html

Install from source
-------------------

Clone the repository and install it locally:

.. code-block:: bash

   git clone https://github.com/avikhagol/avica.git
   cd avica/
   pip install .

Full installation script
------------------------

`install.sh`_ sets up AVICA together with CASA and rPICARD. Run it as your
normal user. The quickest way is to fetch and run it in one step:

.. code-block:: bash

   curl -LsSf https://avikhagol.github.io/avica/install.sh | bash
   source "$HOME/.local/share/avica-stack/env.sh"

.. note::

   Requires ``rsync`` and ``git``.

.. _install.sh: https://github.com/avikhagol/avica/blob/main/install.sh

What the script does
~~~~~~~~~~~~~~~~~~~~

* Installs AVICA with ``uv`` (and installs ``uv`` first if it is missing).
* If ``picard`` is already on ``PATH``, reuses that installation and skips all
  CASA/rPICARD downloads and plotting/data setup.
* Otherwise, installs rPICARD, jiveplot (with ``python-pgplot==1.6.1``), and
  monolithic CASA. The CASA directory is saved in AVICA's global configuration
  with ``avica pipe config --global casadir=...``.
* Adds an environment file to ``~/.bashrc``. It configures AVICA's CASA and
  input-template paths when it can identify them, preserving other settings
  and backing up an existing ``~/.avica/avica.inp``. For an existing
  ``picard`` command, it reads the adjacent rPICARD ``your_casapath.txt`` when
  available; otherwise, existing AVICA settings are left unchanged.

Choosing CASA
~~~~~~~~~~~~~

For a new rPICARD installation, set ``CASA_PATH`` to an existing CASA
installation directory (containing ``bin/casa`` and ``bin/mpicasa``) or an
archive URL:

.. code-block:: bash

   CASA_PATH=/path/to/casa bash install.sh

With the one-liner, place the variable after the pipe so it reaches ``bash``,
not ``curl``:

.. code-block:: bash

   curl -LsSf https://avikhagol.github.io/avica/install.sh | CASA_PATH=/path/to/casa bash

If unset, the script prompts for the location. Press Enter to download the
default archive:

.. code-block:: text

   ftp://ftp.mpifr-bonn.mpg.de/outgoing/mjanssen/casa-6.7.5-18-py3.12.el8.tar.xz

Without an interactive terminal, the same default is used. Choose a CASA
version that matches the selected rPICARD version.

Environment variables
~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Variable
     - Description
   * - ``CASA_PATH``
     - Existing CASA directory or archive URL. ``CASA_DIR`` and ``CASA_URL``
       are also accepted, after ``CASA_PATH`` in that order.
   * - ``AVICA_INSTALL_DIR``
     - Installation directory. Defaults to ``~/.local/share/avica-stack``.
   * - ``AVICA_SOURCE_DIR``
     - Local AVICA source directory to install instead of the latest PyPI
       version.
   * - ``PICARD_REF``
     - Branch or tag for a new rPICARD clone. Defaults to ``master``.

Run ``bash install.sh --help`` (or
``curl -LsSf https://avikhagol.github.io/avica/install.sh | bash -s -- --help``
for the one-liner) to print these options. The previous apt and
dependency-check options have been removed.

Next steps
----------

The pipeline calibration steps rely on `rPICARD`_. Once rPICARD is set up,
AVICA only needs a minimal configuration file to get started; see
:doc:`configuration`.
