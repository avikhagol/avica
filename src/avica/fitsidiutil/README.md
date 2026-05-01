> Under Development
<!-- # fitsidiutil

This repository is for doing effecient and useful fitsidi operations on fitsidi file

>NOTE: uses cfitsio, sofa and pybind11

# Installation

1. Download/git clone this repository and change directory to the repo.
```bash
cd fitsidiutil #cd fitsidi_util
```
2. Install `fitsidiutil` using the pip installer:
```bash
pip install .

```
This will create all the necessary library files. Write to me if your program fails here and you have completed previous steps successfully.
> Note: This requires python3.8 or above. Also needs the development package for Python 3 version being used.

### Current Capabilities:
 - Print Observation summary selecting the Source ID
 - Split sources using a list of baselines or source IDs

## Examples

#### Example 1

```bash
fitsidiutil --help

                                                                                                                                                                                                             
 Usage: fitsidiutil [OPTIONS] COMMAND [ARGS]...                                                                                                                                                              
                                                                                                                                                                                                             
╭─ Options ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --version             -v        Show the version and exit.                                                                                                                                                │
│ --install-completion            Install completion for the current shell.                                                                                                                                 │
│ --show-completion               Show completion for the current shell, to copy it or customize the installation.                                                                                          │
│ --help                          Show this message and exit.                                                                                                                                               │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ split                                                                                                                                                                                                     │
│ listobs                                                                                                                                                                                                   │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

#### Example 2 : Split fitsfile

```bash
fitsidiutil split --help
                                                                                                                                                                                                             
 Usage: fitsidiutil split [OPTIONS] FITSFILEPATH OUTFITSFILEPATH                                                                                                                                             
                                                                                                                                                                                                             
╭─ Arguments ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    fitsfilepath         TEXT  [default: None] [required]                                                                                                                                                │
│ *    outfitsfilepath      TEXT  [default: None] [required]                                                                                                                                                │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --sids                 TEXT  [default: None]                                                                                                                                                              │
│ --baseline-ids         TEXT  [default: None]                                                                                                                                                              │
│ --source-col           TEXT  [default: SOURCE]                                                                                                                                                            │
│ --baseline-col         TEXT  [default: BASELINE]                                                                                                                                                          │
│ --frequency-col        TEXT  [default: FREQUENCY]                                                                                                                                                         │
│ --help                       Show this message and exit.                                                                                                                                                  │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

give the optional comma separated `sids` or `baseline-ids` to select the data for splitting
```bash
fitsidiutil split /path/to/input/fits /path/to/output/fits --sids 1,2
```

#### Example 3 : List Observation details selected by Source IDs

```bash
fitsidiutil listobs --help
                                                                                                                                                                                                             
 Usage: fitsidiutil listobs [OPTIONS] FITSFILEPATH                                                                                                                                                           
                                                                                                                                                                                                             
╭─ Arguments ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    fitsfilepath      TEXT  [default: None] [required]                                                                                                                                                   │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --sids        TEXT  [default: None]                                                                                                                                                                    │
│ --help                 Show this message and exit.                                                                                                                                                        │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

```

give the optional comma separated `sids` or `baseline-ids` to select the data for splitting

```bash
fitsidiutil listobs /path/to/input/fits --sids 1,2
``` -->
