![PyPI - Downloads](https://img.shields.io/pypi/dm/avica)
![GitHub License](https://img.shields.io/github/license/avikhagol/avica)



VLBI and SMILE-based CASA Optimization (VASCO) pipeline has been renamed to AVICA.

# avica
AVICA: Automated VLBI pipeline in CASA


Documentation : https://avica.readthedocs.io/en/latest/

> submitted to A&A

[![asciicast](https://asciinema.org/a/945113.svg)](https://asciinema.org/a/945113)
> Demo of the AVICA pipeline running end-to-end.


# Installation

> Needs Ubuntu 18.04+, Debian 10+, RHEL/CentOS 8+ \
> Python >=3.9
 
Since the monolithic version of casa includes its own internal Python 3 installation, 
it is best to install `avica` within a Python environment that matches the casa version.

<!--Since the monolithic version of casa includes its own internal Python 3 installation, 
it is best to install avica within a Python environment that matches the casa version.

Specifically, if you are not using the "all" installation option, 
you should use the casa Python executable itself to create a virtual environment first. For example, for `casa-6.7.0-31-py3.10.el8/` use a virtual environment created using `Python 3.10`. Conda can be used for creating the environment:
-->

```bash
   
   $ path/to/python3 -m venv MY_ENV_DIR
   $ source MY_ENV_DIR/bin/activate

```

```bash

   $ pip install avica

```

Alternatively, you can use the following installation method, 
which automatically includes the necessary casa dependency for avica's internal operations.

```bash

   $ pip install avica[all]

```

Note that you must still provide the path to your casadir. 
This ensures that the pipeline uses the same monolithic casa version, ideally the one downloaded for 
rPicard to execute specific tasks like mstransform and importfitsidi within an isolated environment.

## Manual

1. Clone the repository to the desired destination.

```
git clone https://github.com/avikhagol/avica.git
```

2. Install using `pip`

```bash
cd avica/

pip install .

```


# Usage


## Pipeline

```
Usage: avica pipe run [OPTIONS] [STPS]...                                                                                                                                                                                                                                                                                    
                                                                                                                                                                                                                                                                                                                              
 _______________________                                                                                                                                                                                                                                                                                                      
                                                                                                                                                                                                                                                                                                                              
 pipeline steps:
 
 -  preprocess_fitsidi
 -  fits_to_ms
 -  phaseshift
 -  avica_avg
 -  avicameta_ms
 -  avica_snr
 -  avica_fill_input
 -  avica_split_ms
 -  rpicard
 
 ________________________                                                     
 
      
╭─ Arguments ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│   stps      [STPS]...  steps for execution [default: preprocess_fitsidi, fits_to_ms, avica_avg, avicameta_ms, avica_snr, avica_fill_input, avica_split_ms, rpicard]                                                                                                                                                        │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --f,--fitsfilenames        TEXT  fitsfile names comma separated                                                                                                                                                                                                                                                            │
│ --t,--target               TEXT  Selected field / sourc name                                                                                                                                                                                                                                                               │
│ --configfile               TEXT  config file containing key=value [default: avica.inp]                                                                                                                                                                                                                                     │
│ --help                           Show this message and exit.                                                                                                                                                                                                                                                               │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯


```

## Manipulating FITS-IDI

To check known FITS-IDI issues run the following:

```
 Usage: avica fitsidi_check [OPTIONS] [FITSFILENAMES]... COMMAND [ARGS]...                                                                                                                                                                                                                                                         
                                                                                                                                                                                                                                                                                                                              
 validate and fix, known FITS-IDI problems                                                                                                                                                                                                                                                                                    
                                                                                                                                                                                                                                                                                                                              
╭─ Arguments ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│   fitsfilenames      [FITSFILENAMES]...                                                                                                                                                                                                                                                                                    │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --fix     --no-fix       [default: no-fix]                                                                                                                                                                                                                                                                                 │
│ --desc    --no-desc      [default: no-desc]                                                                                                                                                                                                                                                                                │
│ --help                   Show this message and exit.                                                                                                                                                                                                                                                                       │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯


```


#### Example

```
avica fitsidi_check VLBA_VSN005412_file3.uvfits
+--------------------+---------+-------+-------+----------------+----------+
| hdu                | fixable | total | fixed | problem_code   | affected |
+==========================================================================+
| ARRAY_GEOMETRY     | 0       | 8     | 0     | []             | []       |
| ANTENNA            | 0       | 16    | 0     | []             | []       |
| FREQUENCY          | 0       | 8     | 0     | []             | []       |
| PHASE-CAL          | 0       | 12    | 0     | []             | []       |
| PRIMARY            | 1       | 10    | 0     | ["extra_byte"] | [""]     |
| SOURCE             | 0       | 8     | 0     | []             | []       |
| FLAG               | 0       | 12    | 0     | []             | []       |
| UV_DATA            | 0       | 8     | 0     | []             | []       |
| GAIN_CURVE         | 0       | 8     | 0     | []             | []       |
| SYSTEM_TEMPERATURE | 0       | 8     | 0     | []             | []       |
+--------------------+---------+-------+-------+----------------+----------+

```


To get the information on the observation run the following:

```
avica listobs [FITSFILENAMES]... 
```


# Development
After you clone the repo
```bash

$ cd avica
$ pip install -e .[dev]
```

# Attribution

When using AVICA, please add a link to this repository in a footnote.

# Acknowledgement

"AVICA was developed within the "Search for Milli-Lenses" (SMILE) project. SMILE has received funding from the European Research Council (ERC) under the HORIZON ERC Grants 2021 programme (grant agreement No. 101040021).
