<div align="center">

# AVICA

**Automated VLBI calibration in CASA**

From raw FITS-IDI files to calibrated data with one command.

[![PyPI - Downloads](https://img.shields.io/pypi/dm/avica?cacheSeconds=3600)](https://pypi.org/project/avica/)
[![Read the Docs](https://readthedocs.org/projects/avica/badge/?version=latest)](https://avica.readthedocs.io/en/latest/)
[![GitHub Release](https://img.shields.io/github/v/release/avikhagol/avica?cacheSeconds=3600)](https://github.com/avikhagol/avica/releases)
[![GitHub Last Commit](https://img.shields.io/github/last-commit/avikhagol/avica?cacheSeconds=3600)](https://github.com/avikhagol/avica/commits)
[![DOI](https://img.shields.io/badge/DOI-10.1051%2F0004--6361%2F202660469-0077B5?style=flat-square)](https://doi.org/10.1051/0004-6361/202660469)



[Documentation](https://avica.readthedocs.io/en/latest/) ·
[Demos](https://avikhagol.github.io/avica-demos) ·
[Install](https://github.com/avikhagol/avica#install) ·
[Quick start](https://github.com/avikhagol/avica#quick-start)

</div>


[![A recorded AVICA pipeline run in the terminal](https://asciinema.org/a/1016974.svg)](https://asciinema.org/a/1016974)

## What it does

AVICA takes VLBI visibilities in FITS-IDI format and walks them through calibration,
one step at a time:

- **Checks your FITS-IDI files** for known problems and fixes the ones it can.
- **Imports them into CASA**, applying station flag files it finds next to your data.
- **Picks calibrators and reference antennas** by rating every scan and baseline on fringe SNR.
- **Calibrates with [rPICARD](https://bitbucket.org/M_Janssen/picard/src/master/)**, with input files filled in for you.
- **Records every step**, so you can see what failed and resume from there.

## Install

Using [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
uv tool install avica --python 3.10
```

`pipx install avica` and `pip install avica` work too. Linux and Python 3.10+ are required.

The calibration steps also need CASA and rPICARD. To install everything at once:

```bash
curl -LsSf https://avikhagol.github.io/avica/install.sh | bash
source "$HOME/.local/share/avica-stack/env.sh"
```

See the [installation guide](https://avica.readthedocs.io/en/latest/installation.html)
for choosing a CASA version, reusing an existing rPICARD, and other options.

## Quick start

**1. Tell AVICA where things are.** Create `avica.inp` in your working folder:

```ini
folder_for_fits = /path/to/folder/with/fitsfiles
casadir         = "/path/to/casa-6.x.x-xx-py3.xx.xxx/"
```

**2. Run the pipeline** for your target:

```bash
avica pipe run --target J0102+5824 --fitsfilenames file1.uvfits,file2.uvfits
```

**3. See how it went:**

```bash
avica pipe result --target J0102+5824
```

This prints one row per step with its status and duration. If a step failed, the
footer shows the command to pick up from there.

A few commands are handy on their own, without running the pipeline:

```bash
avica fitsidi_check file.uvfits    # look for known FITS-IDI problems (add --fix to repair)
avica listobs file.uvfits          # scan-by-scan summary of an observation
avica pipe config --summary        # every setting, its value, and where it came from
```

## Documentation

| Guide | What's inside |
| --- | --- |
| [Installation](https://avica.readthedocs.io/en/latest/installation.html) | PyPI, from source, and the CASA + rPICARD installer |
| [Configuration](https://avica.readthedocs.io/en/latest/configuration.html) | `avica.inp`, saved defaults, parameter summary, cleaning up |
| [Pipeline](https://avica.readthedocs.io/en/latest/pipeline.html) | What each step does, flag files, results, and logs |
| [Examples](https://avica.readthedocs.io/en/latest/examples.html) | Sample output and Python usage |
| [API reference](https://avica.readthedocs.io/en/latest/api.html) | Python modules |
| [Demos](https://avikhagol.github.io/avica-demos) | Terminal recordings of common tasks |

## Contributing

Bug reports, questions and pull requests are welcome. Start with
[CONTRIBUTING.md](https://github.com/avikhagol/avica/blob/main/CONTRIBUTING.md) or [open an issue](https://github.com/avikhagol/avica/issues).

## Citing AVICA

If you use AVICA in your research, please cite our [https://doi.org/10.1051/0004-6361/202660469](https://doi.org/10.1051/0004-6361/202660469).

## Acknowledgement

AVICA was developed within the "Search for Milli-Lenses" (SMILE) project. SMILE has
received funding from the European Research Council (ERC) under the HORIZON ERC Grants
2021 programme (grant agreement No. 101040021).

## License

[MIT](https://github.com/avikhagol/avica/blob/main/LICENSE) © Avinash Kumar
