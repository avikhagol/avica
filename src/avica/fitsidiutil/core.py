from typing import Any, TYPE_CHECKING
from ._core import ReadIO, split, RowData, HeaderManager, HeaderCard, repair_hdu_key

__all__ = ["split","ReadIO","__doc__", "RowData", "HeaderManager", "HeaderCard", 'repair_hdu_key']


class HeaderWrapper:
    def __init__(self, reader: "ReadIO", hdu_num: int):
        self._reader: "ReadIO" = reader
        self.hdu_num = hdu_num

    def update_key(self, key: str, new_value: Any, comment: str = ""):
        ...
        
def repair_hdu_key(
    filep: str, 
    hdu_num: int, 
    card_pos: int, 
    key: str, 
    value: int, 
    comm: str, 
    shift: bool = True
        ) -> None:
    """repairs or inserts a FITS header keyword in a specific HDU.

    :param filep: Full path to the .fits file.
    :param hdu_num: 1-indexed HDU number (1 = Primary, 2 = First Extension).
    :param card_pos: The 1-indexed slot position (e.g., 3 for the 3rd card). 
                     Ignored if shift=False.
    :param key: The 8-character FITS keyword name (e.g., 'NAXIS').
    :param value: The integer value to assign to the keyword.
    :param comm: The comment string for the keyword.
    :param shift: If True, inserts a new card and pushes subsequent cards down.
                  If False, searches for 'key' by name and updates it in place.
    """
    ...