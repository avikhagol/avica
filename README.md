# vasco
VASCO: VLBI and SMILE source based CASA Optimizations

This is a helper tool for CASA based optimizations to use rPICARD and CASA for VLBI in general and in particular for the SMILE sources.

# Example

```bash
$ vasco -l "SCAN,SOURCE,ANTENNA" -f test.fits > list.obs
```

# USAGE
```bash
usage: vasco [-h] [-f INPUT_FILE] [-plist PARAMETER_LIST] [-l [LIST_OBSERVATION]]

VLBI and SMILE source based CASA Optimizations (VASCO).

optional arguments:
  -h, --help            show this help message and exit
  -f INPUT_FILE, --input-file INPUT_FILE
                        Give the input file path.

plotting:
  
                                     use plotms based arguments to generate plots in the terminal.

  -plist PARAMETER_LIST, --parameter-list PARAMETER_LIST
                        list of parameters comma separated to fill in plotms

operations:
  
                               use operations based on file type e.g., .FITS .MS

  -l [LIST_OBSERVATION], --list-observation [LIST_OBSERVATION]
                        lists all the useful details similar to listobs in CASA.
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