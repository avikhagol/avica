
- [Contents:](#contents)
  - [About](#about)
  - [Installation](#installation)
  - [Usage](#usage)
  - [Manipulating FITS-IDI files](#manipulating-fits-idi)
  - [Attribution](#attribution)
  - [Acknowledgement](#acknowledgement)

>Note: 
>- Submitted to A&A
>- VLBI and SMILE-based CASA Optimization pipeline has been renamed to AVICA.


# About
AVICA: Automated VLBI pipeline in CASA


Demo of the AVICA pipeline running end-to-end:

[![asciicast](https://asciinema.org/a/1016974.svg)](https://asciinema.org/a/1016974)

Documentation : https://avica.readthedocs.io/en/latest/


# Installation

> Requires Ubuntu 18.04+, Debian 10+, RHEL/CentOS 8+ \
> Python >=3.9
 

The recommended way to install `avica` is by using the `pipx` package manager. This installs `avica` into a
dedicated virtual environment and adds it to your `PATH`. Installation instructions for `pipx` can be found at [this link](https://pipx.pypa.io/stable/how-to/install-pipx/).

```bash
  # python3 -m pip install --user pipx
  pipx install avica
```

Alternatively, you can install `avica` within a Python environment.

```bash
   python3 -m venv /path/to/env
   source /path/to/env/bin/activate
   python3 -m pip install avica

```

Note that you must provide the path to your monolithic casa directory in the configuration file.
This ensures that the pipeline uses the same monolithic casa version, ideally the one downloaded for 
rPicard. For more details, see: [documentation](https://avica.readthedocs.io/en/latest/).

### Manual

1. Clone the repository to the desired destination.

```bash
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

<!--
# Development
After you clone the repo
```bash

$ cd avica
$ pip install -e .[dev]
```-->

# Attribution

When using AVICA, please add a link to this repository in a footnote.

# Acknowledgement

"AVICA was developed within the "Search for Milli-Lenses" (SMILE) project. SMILE has received funding from the European Research Council (ERC) under the HORIZON ERC Grants 2021 programme (grant agreement No. 101040021).
