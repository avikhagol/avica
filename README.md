# vasco
VASCO: VLBI and SMILE source based CASA Optimizations

This is a helper tool for CASA based optimizations to use rPICARD and CASA for VLBI in general and in particular for the SMILE sources.

# Example

### Example 1: To print or save a summary of the observation from the fitsfile

```bash
$ vasco -l SCAN test.fits     # shows the scan summary
$ vasco -l "SCAN,SOURCE,ANTENNA" test.fits > list.obs # saves the scan summary, source and antenna table to list.obs file
```

### Example 2: To search through the calibrator list e.g VLBA calibrator list.
> Automatic setup on first run of the command `-S`
```bash
$ vasco -S 0851+071           # search for source '0851+071' in the catalog
Category  IVS name  J2000 name hh(RA) mm(RA)     ss(RA) dd(DEC) mm(DEC)     ss(DEC)   D_alp   D_Del    Corr     Obs S_T-  ... X_T-  X_Tot X_u- X_unres U_T-  U_Tot U_u- U_unres K_T-  K_Tot K_u- K_unres Type       Cat
8296        C  0851+071  J0853+0654     08     53  48.189960     +06      54  47.23480      0.11    0.13  -0.065     686       ...       0.466        0.180    -  1.00     -   1.00     -  1.00     -   1.00   Fus  rfc_2023

$ vasco -S 0851+071 -C C_Tot  # sources shown with desired Columns only
C_Tot
8296  0.628
```

### Example 3: To find reference antenna using TSYS, number of rows, centroid distance.

```bash

$ vasco --find-refant path/to/fits/     # or use -r
VLBA_BK225_bk225_BIN0_SRC0_0_200331T185856.idifits
ANNAME  STD_TSYS  nRows    Distance        c
    LA  0.738351    381 1260.435131 0.917150
    KP  0.323148    377 1379.696201 0.910588
    FD  0.225693    381 1581.388142 0.903156
    OV  1.517222    380 1361.275357 0.902314
    PT  3.077450    380 1318.495946 0.889056
    BR  1.590541    381 2107.213672 0.857879
    HN  3.164951    381 3166.169909 0.778600
    SC  4.137334    381 4519.400894 0.687829
    NL 20.632759    381 1869.867131 0.679032
    MK 35.641647    381 4883.011027 0.346715

$ vasco -r /path/to/measurement/set     # in Progress for terminal use

$ mpicasa -n N_CORES /path/to/casa -c /path/to/vasco -r /path/to/MSFILE --mpi # one can use mpicasa to execute the short fringe fit step which gives the refant.

```

### Example 4: To identify targets using the sequence in the scan list and the position to find a possible pair. 
If `-S SOURCE_NAME` is invoked on a fitsfile then flux information from the calibrator list is used and SNR information is used in case of Measurement Set.
> Note: run `vasco -r MSFILE` before using this command on Measurement Set as the program looks for the required metafile.

```bash
$ vasco path/to/fits --identify-targets  # or use -t
ec071d_1_1.IDI1
{
'calibrators_instrphase': ['J0927+3902', 'J1310+3220'], 
'calibrators_bandpass': ['J0927+3902', 'J1310+3220'], 
'calibrators_rldly': None, 
'calibrators_dterms': None, 
'calibrators_phaseref': ['J1148+1840'], 
'science_target': ['J1143+1834']
}

$ vasco path/to/fits -t -S SOURCE_NAME
is phref
target is phref calib
target is in phref but ps not found
{'calibrators_instrphase': ['J1224+2122', '1321+045'], 'calibrators_bandpass': ['J1224+2122', '1321+045'], 
'calibrators_rldly': None, 'calibrators_dterms': None, 
'calibrators_phaseref': None, 
'science_target': ['J1332+0200']
}

$ vasco path/to/measurement/set -t -S SOURCE_NAME  # run after short fringefit step
path/to/measurement/set
is phref
target was phref calib (from sequence)
target is in phref but no suitable calibrator pair found
C band
{'calibrators_instrphase': ['1321+045', 'J1224+2122', 'J1332+0200'], 'calibrators_bandpass': ['1321+045', 'J1224+2122', 'J1332+0200'], 'calibrators_rldly': None, 'calibrators_dterms': None, 'calibrators_phaseref': None, 'science_target': None
}

```

# USAGE

```bash
usage: vasco [-h] [--wd WD] [--mpi MPI] [--ants ANTS] [--spws SPWS] [-S SOURCES] [--from-meta] [--from-snr] [-o OUTPUT_FILE] [-l [LIST_OBSERVATION]] [-t] [-r] [-s SPLIT_SOURCE] [--to-B TO_B] [-C COLUMN] [input_file [input_file ...]]

____    ____  ___           _______.  ______   ______   
\   \  /   / /   \         /       | /      | /  __  \  
 \   \/   / /  ^  \       |   (----`|  ,----'|  |  |  | 
  \      / /  /_\  \       \   \    |  |     |  |  |  | 
   \    / /  _____  \  .----)   |   |  `----.|  `--'  | 
    \__/ /__/     \__\ |_______/     \______| \______/  

    VLBI and SMILE source based CASA Optimizations (VASCO).                                                        
    
    

positional arguments:
  input_file            Give the input file path.

optional arguments:
  -h, --help            show this help message and exit
  --wd WD               current workdir; path used for the metafolder.
  --mpi MPI             use mpi when available
  --ants ANTS           selected antennas, used for running operations using these antennas only
  --spws SPWS           selected spws, used for running operations using these spws only
  -S SOURCES, --sources SOURCES
                        selected fields i.e source names for operations.
  --from-meta           useful to run operations without determining metadata and tables again
  --from-snr            to find sources from snr data second input in --input-file is the snr metafile; should have .vasco in path; also needs --output-file else only prints output
  -o OUTPUT_FILE, --output-file OUTPUT_FILE
                        Give the output file path.

operations:
  
                               use operations based on file type e.g., .FITS .MS

  -l [LIST_OBSERVATION], --list-observation [LIST_OBSERVATION]
                        lists all the useful details similar to listobs in CASA or listr in AIPS.
  -t, --identify-targets
                        find targets for phasecal, science and bright cal for FF
  -r, --find-refant     find refant by checking TSYS info
  -s SPLIT_SOURCE, --split-source SPLIT_SOURCE
                        comma separated values of SOURCE_ID/SOURCE_NAME is used to select Sources to create a new FITS file/ MS.
  --to-B TO_B           Convert to B1920

Calibrator List:
  
                               use source based search on the calibrator list file.

  -C COLUMN, --column COLUMN
                        Comma separated values of column to get value for
```

# Installation
After you clone the repo
```bash

$ cd vasco
$ pip install .
```


# Development
After you clone the repo
```bash

$ cd vasco
$ pip install -e .[dev]
```

# Attribution

When using VASCO, please add a link to this repository in a footnote.

# Acknowledgement

"VASCO was developed within the "Search for Milli-Lenses" (SMILE) project. SMILE has received funding from the European Research Council (ERC) under the HORIZON ERC Grants 2021 programme (grant agreement No. 101040021).