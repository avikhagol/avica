# vasco
VASCO: VLBI and SMILE source based CASA Optimizations

> submitted to A&A


# Installation


```bash

pip install vasco
```

## Manual

```
git clone --recurse-submodules https://github.com/avikhagol/vasco.git
```

# Usage


## Pipeline

```
Usage: vasco pipe run [OPTIONS] [STPS]...                                                                                                                                                                                                                                                                                    
                                                                                                                                                                                                                                                                                                                              
 _______________________                                                                                                                                                                                                                                                                                                      
                                                                                                                                                                                                                                                                                                                              
 pipeline steps:
 
 -  preprocess_fitsidi
 -  fits_to_ms
 -  phaseshift
 -  vasco_avg
 -  vascometa_ms
 -  vasco_snr
 -  vasco_fill_input
 -  vasco_split_ms
 -  rpicard
 
 ________________________                                                     
 
      
╭─ Arguments ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│   stps      [STPS]...  steps for execution [default: preprocess_fitsidi, fits_to_ms, vasco_avg, vascometa_ms, vasco_snr, vasco_fill_input, vasco_split_ms, rpicard]                                                                                                                                                        │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --f,--fitsfilenames        TEXT  fitsfile names comma separated                                                                                                                                                                                                                                                            │
│ --t,--target               TEXT  Selected field / sourc name                                                                                                                                                                                                                                                               │
│ --configfile               TEXT  config file containing key=value [default: vasco.inp]                                                                                                                                                                                                                                     │
│ --help                           Show this message and exit.                                                                                                                                                                                                                                                               │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯


```

## Manipulating FITS-IDI

To check known FITS-IDI issues run the following:

```
 Usage: vasco fitsidi_check [OPTIONS] [FITSFILENAMES]... COMMAND [ARGS]...                                                                                                                                                                                                                                                         
                                                                                                                                                                                                                                                                                                                              
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
vasco fitsidi_check VLBA_VSN005412_file3.uvfits
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
vasco listobs [FITSFILENAMES]... 
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