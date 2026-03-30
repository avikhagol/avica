
Examples
=======



Example 1.
======


.. jupyter-execute::
   
   ff = 'tests/tes2.fits'

   from vasco.fitsidiutil.obs import ListObs

   lobs = ListObs(ff)

   print(lobs.df_listobs)
   
