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

Getting started
===============

About
=====
VLBI and SMILE-based CASA optimizations using rPICARD pipeline.


Installation
======
   
.. code-block:: bash

   $ pip install vasco[all]


Setup
=====
.. code-block:: bash

   $ vasco setup vasco_pipe

Configuration
=========
.. code-block:: toml

   [vasco_pipe]
   rpicard_path = /path/to/rPicard

Index
==================

* :ref:`genindex`
* :ref:`search`