from __future__ import annotations

# from ._core import split, listobs
from ._core import split, listobs, RowData, rm_hdr
from vasco.fitsidiutil.cli import fitsidiutil_cli

__all__ = ["split","rm_hdr","listobs","__doc__", "__version__", "RowData"]