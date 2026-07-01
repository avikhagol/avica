![PyPI - Downloads](https://img.shields.io/pypi/dm/avica?cacheSeconds=3600)
[![Read the Docs](https://readthedocs.org/projects/avica/badge/?version=latest)](https://avica.readthedocs.io/en/latest/)
![GitHub Release](https://img.shields.io/github/v/release/avikhagol/avica?cacheSeconds=3600)
![GitHub Last Commit](https://img.shields.io/github/last-commit/avikhagol/avica?cacheSeconds=3600)

# AVICA: Automated VLBI pipeline in CASA

**Submitted to A&A**

[![asciicast](https://asciinema.org/a/1016974.svg)](https://asciinema.org/a/1016974)
> Demo of the AVICA pipeline running end-to-end.
Documentation : https://avica.readthedocs.io/en/latest/


# Installation

> Requires Ubuntu 18.04+, Debian 10+, RHEL/CentOS 8+ \
> Python >=3.9

The `avica` package is publicly available on [PyPI](https://pypi.org/project/avica/).
Installation is recommended using [uv](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer) or [pipx](https://pipx.pypa.io/stable/how-to/install-pipx/) within a isolated environment:

using `uv`

```bash
uv tool install avica --python 3.10
```

or using `pipx`

```bash
pipx install avica
```

or using `pip`

```bash
pip install avica
```
> Note: it is recommended to use `venv` for installation, if you are not using `pipx` or `uv`.

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

Since the pipeline's calibration features rely on [rPicard](https://bitbucket.org/M_Janssen/picard/src/master/) please follow the linked setup instructions first. Once rPicard is properly configured, you only need a minimal avica configuration file to get started. (see [Configuration](#configuration))

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

### Configuration

The pipeline configuration is defined in a custom file with key=value defaults to `avica.inp` in the current directory. See the [example](src/avica/pipe/avica_example.inp) for a minimal configuration.
To store default values persistently, create a `avica.inp` file in your home directory (`~/.avica/avica.inp`) using the following command, the default value is used if no `avica.inp` file is found:

```bash
avica pipe config --default --inpfile <path/to/avica.inp>
```

or 
```bash
avica pipe config --default key=value key2=value2 key3=value3
```

# Attribution

When using AVICA, please add a link to this repository in a footnote.

# Acknowledgement

"AVICA was developed within the "Search for Milli-Lenses" (SMILE) project. SMILE has received funding from the European Research Council (ERC) under the HORIZON ERC Grants 2021 programme (grant agreement No. 101040021).
