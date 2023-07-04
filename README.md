# vasco
VASCO: VLBI and SMILE source based CASA Optimizations

This is a helper tool for CASA based optimizations to use rPICARD and CASA for VLBI in general.

# USAGE
```bash
usage: vasco [-h] [-plist PARAMETER_LIST]

VLBI and SMILE source based CASA Optimizations (VASCO).

optional arguments:
  -h, --help            show this help message and exit

plotting:
  use plotms based arguments to generate plots in the terminal.

  -plist PARAMETER_LIST, --parameter-list PARAMETER_LIST
                        list of parameters comma separated to fill in plotms
```

# Development
After you clone the repo
```bash

$ cd vasco
pip install -e .[dev]
```