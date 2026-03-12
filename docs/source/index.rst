.. vasco documentation master file, created by
   sphinx-quickstart on Thu Mar 12 15:27:27 2026.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

vasco documentation
===================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

**************************************
            VASCO
**************************************

Getting started
===============


   
.. code-block:: bash

   $ pip install vasco
    

.. jupyter-execute::
   
   ff = 'tests/tes2.fits'

   from vasco.fitsidiutil.obs import ListObs

   lobs = ListObs(ff)

   print(lobs.df_listobs)
   


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   vasco
   examples


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`