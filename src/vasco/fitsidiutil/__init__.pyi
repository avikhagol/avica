from __future__ import annotations
from typing import List, Any

__all__: list[str]

def listobs(fitsfilepath: str, sids: List[int] = List) -> Any: ...
def split(fitsfilepath: str, outfitsfilepath: str, sids: List[int] = [], baseline_ids: List[int] = List, freqids : List[int] = List,
          source_col : str = "SOURCE", baseline_col : str = "BASELINE", frequency_col : str = "FREQID",
          expression : str = "", reindex : bool = False, verbose : bool = True,
          ) -> Any: ...
def rm_hdr(fitsfilepath: str, hdu_index: int) -> Any: ...
__doc__: str
__version__: str