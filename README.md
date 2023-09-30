# vasco
VASCO: VLBI and SMILE source based CASA Optimizations

This is a helper tool for CASA based optimizations to use rPICARD and CASA for VLBI in general and in particular for the SMILE sources.

# Example

```bash
$ vasco -l "SCAN,SOURCE,ANTENNA" test.fits > list.obs
$ vasco path/to/fits --identify-targets
ec071d_1_1.IDI1
science:['J1143+1834']

phase:['J1148+1840']

brightcal:['J0927+3902', 'J1310+3220']

$ vasco --find-refant path/to/fits/
ec071e_1_1.IDI9
ANNAME  STD_TSYS  nRows   Distance
    JB 15.055768   7880 269.581752
    TR 37.115318   6795 205.491414
    SR 42.076019   2717 270.728365
    O6 74.425308   4383 234.552076

```

# USAGE

```bash
usage: vasco [-h] [-plist PARAMETER_LIST] [-l [LIST_OBSERVATION]] [-t] [-r]
             input_file [input_file ...]

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

plotting:
  
                                     use plotms based arguments to generate plots in the terminal.

  -plist PARAMETER_LIST, --parameter-list PARAMETER_LIST
                        list of parameters comma separated to fill in plotms

operations:
  
                               use operations based on file type e.g., .FITS .MS

  -l [LIST_OBSERVATION], --list-observation [LIST_OBSERVATION]
                        lists all the useful details similar to listobs in
                        CASA or listr in AIPS.
  -t, --identify-targets
                        find targets for phasecal, science and bright cal for
                        FF
  -r, --find-refant     find refant by checking TSYS info
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