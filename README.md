![PyPI - Downloads](https://img.shields.io/pypi/dm/avica?cacheSeconds=3600)
[![Read the Docs](https://readthedocs.org/projects/avica/badge/?version=latest)](https://avica.readthedocs.io/en/latest/)
![GitHub Release](https://img.shields.io/github/v/release/avikhagol/avica?cacheSeconds=3600)
![GitHub Last Commit](https://img.shields.io/github/last-commit/avikhagol/avica?cacheSeconds=3600)

# AVICA: Automated VLBI pipeline in CASA

**Accepted for publication in Astronomy & Astrophysics journal.**

[![asciicast](https://asciinema.org/a/1016974.svg)](https://asciinema.org/a/1016974)

Full documentation: https://avica.readthedocs.io/en/latest/

## Contents

- [Installation](#installation)
  - [Recommended installation](#recommended-installation)
  - [Manual installation](#manual-installation)
- [Usage](#usage)
  - [Pipeline](#pipeline)
  - [Manipulating FITS-IDI](#manipulating-fits-idi)
  - [Configuration](#configuration)
    - [Parameter summary](#parameter-summary)
    - [Cleaning up intermediate data](#cleaning-up-intermediate-data)
- [Attribution](#attribution)
- [Acknowledgement](#acknowledgement)


## Installation

Requirements:

- Ubuntu 18.04+, Debian 10+, or RHEL/CentOS 8+
- Python >= 3.9

The `avica` package is publicly available on [PyPI](https://pypi.org/project/avica/).
Use [uv](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer) or [pipx](https://pipx.pypa.io/stable/how-to/install-pipx/) for an isolated command-line installation.

### Recommended installation

Using `uv`:

```bash
uv tool install avica --python 3.10
```

Using `pipx`:

```bash
pipx install avica
```

Using `pip`:

```bash
pip install avica
```

If you install with `pip`, use a virtual environment unless you already manage Python packages another way.

### Manual installation

Clone the repository and install it locally:

```bash
git clone https://github.com/avikhagol/avica.git
cd avica/
pip install .
```


## Usage

The pipeline calibration steps rely on [rPicard](https://bitbucket.org/M_Janssen/picard/src/master/). Follow the rPicard setup instructions first. After rPicard is configured, AVICA only needs a minimal configuration file to get started; see [Configuration](#configuration).

### Pipeline

Run the default pipeline:

```bash
avica pipe run --fitsfilenames <file1.uvfits,file2.uvfits> --target <source-name>
```

The default pipeline executes these steps:

- `preprocess_fitsidi`
- `fits_to_ms`
- `phaseshift`
- `avica_avg`
- `avicameta_ms`
- `avica_snr`
- `avica_fill_input`
- `avica_split_ms`
- `rpicard`

You can pass one or more step names to run only part of the pipeline:

```bash
avica pipe run preprocess_fitsidi fits_to_ms --fitsfilenames <file.uvfits>
```

Common options:

| Option | Description |
| --- | --- |
| `--f`, `--fitsfilenames` | Comma-separated FITS-IDI file names. |
| `--t`, `--target` | Selected field or source name. |
| `--configfile` | Configuration file containing `key=value` entries. Defaults to `avica.inp`. |
| `--help` | Show the full command help. |

### Manipulating FITS-IDI

Check FITS-IDI files for known issues:

```bash
avica fitsidi_check <file.uvfits>
```

Useful options:

| Option | Description |
| --- | --- |
| `--fix`, `--no-fix` | Apply available fixes. Defaults to `--no-fix`. |
| `--desc`, `--no-desc` | Show issue descriptions. Defaults to `--no-desc`. |
| `--help` | Show the full command help. |

Example output:

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

List observation information:

```bash
avica listobs <file.uvfits>
```

### Configuration

[![asciicast](https://asciinema.org/a/mBmNuDbzI1S2dpqN.svg)](https://asciinema.org/a/mBmNuDbzI1S2dpqN)

The pipeline configuration is a `key=value` file. By default, AVICA looks for `avica.inp` in the current directory. See the [example configuration](src/avica/pipe/avica_example.inp) for a minimal setup.

Pass a custom configuration file with `--configfile`:

```bash
avica pipe run --configfile <path/to/config/file>
```

If `--configfile` is not provided, AVICA uses `avica.inp` by default.

To store defaults persistently, create `~/.avica/avica.inp` from an existing file:

```bash
avica pipe config --default --inpfile <path/to/avica.inp>
```

You can also set default values directly:

```bash
avica pipe config --default key=value key2=value2 key3=value3
```

To set global defaults in AVICA's installed directory, use `--global` in the same way:

```bash
avica pipe config --global --inpfile <path/to/avica.inp>
avica pipe config --global key=value key2=value2 key3=value3
```

To supersede the rPicard `input_template` files (`array.inp`, `observation.inp`, `array_finetune.inp`, `flagging.inp`, `constants.inp`) used by the `rpicard` step, point `picard_input_template_update` at a folder containing the parameters you want to fix:

```text
picard_input_template_update   =   "path/to/folder/with/fixed/inp/files"
```

#### Parameter summary

Use `--summary` to print a report of every pipeline parameter, its resolved value, and where that value came from (`inpfile`, `default`, `context`, or a per-step override):

```bash
avica pipe config --summary --inpfile <path/to/avica.inp>
```

If `--inpfile` is omitted and `avica.inp` exists in the current directory, it's read automatically. Combine `--summary` with `key=value` overrides on the command line to preview how they would change the resolved configuration before writing it out.

#### Cleaning up intermediate data

Each pipeline step can remove its own intermediate files (temporary files, superseded Measurement Sets, etc.) once it finishes. This is controlled by:

| Option | Description |
| --- | --- |
| `delete_removables` | Master switch; must be `True` for any cleanup to happen. Defaults to `False`. |
| `removables` | List of glob patterns (relative to the step's working directory) to delete. Can be set globally or per step as `<step_name>.removables`. |
| `rm_pre` / `<step_name>.rm_pre` | If `True`, delete the matching files *before* the step runs instead of after. |
| `rm_only` | Only perform the deletion and skip running the step itself. |

Several steps ship with sensible defaults, e.g.:

```text
delete_removables            =   True
preprocess_fitsidi.removables    =   ["raw/*.tmp"]
rpicard.removables               =   ["wd_[SLKQXPD]/VLBI_*.ms"]
fits_to_ms.removables            =   ["*.old"]
```

Deletion is always confined to the step's working directory; patterns that resolve outside it are ignored.

## Attribution

When using AVICA, please add a link to this repository in a footnote.

## Acknowledgement

AVICA was developed within the "Search for Milli-Lenses" (SMILE) project. SMILE has received funding from the European Research Council (ERC) under the HORIZON ERC Grants 2021 programme (grant agreement No. 101040021).
