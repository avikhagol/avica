from collections import UserList
from pathlib import Path
from traceback import print_exc
from typing import Any, Dict, List, Optional, Type, TypeAlias, Union
from warnings import warn

import polars as pl

from .core import HeaderManager, ReadIO

FitsValue: TypeAlias = Union[str, int, float, bool]
HeaderCardDict: TypeAlias = Dict[str, Union[str, FitsValue, int]]


pl.Config(
    ascii_tables=True,  # Use +--+ instead of Unicode boxes
    tbl_hide_column_data_types=True,
    tbl_hide_dataframe_shape=True,
    tbl_width_chars=10000,
    float_precision=4,
    tbl_rows=-1,
    tbl_cols=-1,
)

# --------------------------------------------------------------

global CLASS_ATTRS
CLASS_ATTRS = {"cards"}


L = 76
I = 73
C = 67
F = 70
X = 88


FITS_TYPE_MAP = {
    L: {"code": "L", "name": "Logical", "type": bool},
    I: {"code": "I", "name": "Integer", "type": int},
    C: {"code": "C", "name": "String", "type": str},
    F: {"code": "F", "name": "Float", "type": float},
    X: {"code": "X", "name": "Complex", "type": complex},
}

# --------------------------------------------------------------


def read_idi(
    fitsfile, max_chunk=None, start_row=0, chunk_cols=["UV_DATA"], **read_kwargs
):
    """read the table data using chunk, by default reads 1 row for the specified column.

    Note:
        if max_chunk=None, only single rows are read for the specified chunk_cols.

    Args:
        fitsfile (_type_): _description_
        max_chunk (int, optional): maximum number of chunks. Defaults to None.
        start_row (int, optional): row to start readin from. Defaults to 0.
        chunk_cols (list, optional): filter chunking only on the selected columns. Defaults to ['UV_DATA'].

    Returns:
        idiHDUList: The HDU list read from the FITS-IDI file.
    """
    return FITSIDI.quickread(
        fitsfile,
        mode="r",
        max_chunk=max_chunk,
        start_row=start_row,
        chunk_cols=chunk_cols,
        **read_kwargs,
    )


class FITSIDI:
    """
    - Read IDIFITS file
    - use .df with hdu to show data in a polars DataFrame.
    - Update headers and table data by columns

    Note:
            Write mode is experimental, use with caution.

    Example
    -------

    .. code-block:: python

        with FITSIDI(fitsfilepath).open('r') as fo:
            hdul = fo.read()

        # or
        from avica.fitsidiutil import read_idi
        hdul = read_idi(fitsfilepath)

    """

    def __init__(self, fitsfile, mode="r"):
        self.fitsfile = fitsfile
        self.mode = mode
        self.hdul = None
        self._reader = None

    def open(self, mode=None):
        if mode is not None:
            self.mode = mode
        self._reader = ReadIO()
        if not self._reader.open(self.fitsfile, writeable="w" in self.mode):
            raise IOError(f"Could not open FITS file: {self.fitsfile}")
        return self

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """automatically closes the file when the 'with' block ends."""
        self.close()

    def __del__(self):
        if hasattr(self, "_reader"):
            del self._reader
            self._reader = None

    def __load_idi_headers(self):
        header_mgr = self._reader.header_mgr

        hdu_objects = IdiHeaderHDUList()

        for hdu_num, card_list in header_mgr.all_hdus.items():
            clean_kwargs = {}
            dtype_map = {}

            for card in card_list:
                dtype = card.type
                python_type = FITS_TYPE_MAP[dtype]["type"]
                if str(python_type) == "bool":
                    clean_kwargs[card.key] = str(card.value)  # .startswith("T") == True
                else:
                    clean_kwargs[card.key] = python_type(card.value)
                dtype_map[card.key] = dtype

            hdu_history = header_mgr.history.get(hdu_num, [])
            hdu_comments = header_mgr.comments.get(hdu_num, [])

            hdu_objects.append(
                IdiHDUHeader(
                    history=hdu_history,
                    comments=hdu_comments,
                    dtypes=dtype_map,
                    **clean_kwargs,
                )
            )
        return hdu_objects

    # def fix_naxis(self):  # TODO: method to add NAXIS when NAXIS is not present, CFITSIO throws error in normal circumstances.
    #     self._reader.repair_naxis()

    def check_extrabytes(self, verbose=True):
        extra_byte_location = None
        actual_size, expected_size = self._reader.get_fits_byte_size()
        if actual_size - expected_size > 0:
            extra_byte_location = expected_size
            if verbose:
                print(
                    f"found {actual_size - expected_size} byetes at location {extra_byte_location}"
                )
        elif actual_size - expected_size < 0:
            if verbose:
                print(
                    f"truncated: missing {expected_size - actual_size} bytes at location {actual_size}"
                )
        return extra_byte_location

    def close(self):
        self._reader.close()
        if hasattr(self, "_reader"):
            del self._reader
            self._reader = None

    def flush(self):
        self._reader.flush()

    def iter_read(self, total_rows, size_chunk=50_000, chunk_cols=["UV_DATA"]):
        """Allows to iterate by chunk by returning a hdul generator.

        Args:
            total_rows (int): total number of rows.
            size_chunk (int, optional): size of chunk in number of rows. Defaults to 50_000.
            chunk_cols (list, optional): filter chunking only on the selected columns. Defaults to ['UV_DATA'].

        Yields (generator):
            hdul: (FITSIDI.idiHDUList)

        Example:
        --------

        .. code-block:: python

            hdul_gen =fo.iter_read(total_rows, size_chunk=size_chunk)
            source_id_uvdata = set()
            for i, hdul in enumerate(hdul_gen):
                source_found_in_chunk = (
                    hdul['UV_DATA'].df
                        .select('SOURCE')
                        .unique()
                        .to_series()
                        .to_list()
                    )
                source_id_uvdata.update(found_in_chunk))

        """
        for start_row in range(0, total_rows, size_chunk):
            rows_to_read = min(size_chunk, total_rows - start_row)
            current_hdu_chunk = self.read(
                rows_to_read, start_row=start_row, chunk_cols=chunk_cols
            )
            yield current_hdu_chunk
            current_hdu_chunk = None

    @classmethod
    def quickread(cls, fitsfile, mode="r", **read_kwargs):
        """read the table data using chunk, by default reads 1 row.

        Args:
            max_chunk (int, optional): maximum number of chunks. Defaults to None.
            start_row (int, optional): row to start readin from. Defaults to 0.
            chunk_cols (list, optional): filter chunking only on the selected columns. Defaults to ['UV_DATA'].

            NOTE: if max_chunk=None, only single rows are read for the specified chunk_cols.

        Returns:
            hdul (FITSIDI.idiHDUList)
        """
        with cls(fitsfile).open(mode) as fo:
            return fo.read(**read_kwargs)

    def read(self, max_chunk=None, start_row=0, chunk_cols=["UV_DATA"]):
        """read the table data using chunk, by default reads 1 row.

        Args:
            max_chunk (int, optional): maximum number of chunks. Defaults to None.
            start_row (int, optional): row to start readin from. Defaults to 0.
            chunk_cols (list, optional): filter chunking only on the selected columns. Defaults to ['UV_DATA'].

            NOTE: if max_chunk=None, only single rows are read for the specified chunk_cols.

        Returns:
            hdul (idiHDUList)
        """
        if not self._reader:
            self.open()

        self._reader.fetch_header()
        self.hdus = self.__load_idi_headers()

        if max_chunk is None:
            max_chunk = 0

        try:
            self.hdul = IdiHDUList()

            for i, header in enumerate(self.hdus):
                _start_row = start_row
                _hdu_num = i + 1
                _data = None

                nrows = min(header.dim[0], abs(max_chunk))

                total_rows = header.dim[0]
                end_row = start_row + nrows

                if end_row > total_rows or start_row > total_rows:
                    end_row = total_rows
                    _start_row = 0

                if len(chunk_cols) and (header.extension_name not in chunk_cols):
                    end_row = total_rows
                    _start_row = 0

                _data = IdIHDU(
                    header_data=header,
                    table_data=self._reader.read_table_chunked(
                        _hdu_num, _start_row, end_row
                    ),
                    hdu_num=_hdu_num,
                    reader=self._reader,
                )
                self.hdul.append(_data)
            self.hdul.extra_byte_location = self.check_extrabytes(verbose=False)
            self.hdul.filename = self.fitsfile

        except Exception as e:
            print_exc()

        return self.hdul

    def save_as(self, outputfile: str, verbose: bool = False):
        if not self._reader:
            raise RuntimeError("No file open.")

        uv_dict_by_idx = {}

        if self.hdul is not None:
            uv_idx = 0
            for hdu in self.hdul:
                if hdu.extension_name == "UV_DATA" and hdu.df is not None:
                    uv_dict_by_idx[uv_idx] = {
                        col: hdu.df[col].to_numpy() for col in hdu.df.columns
                    }
                    uv_idx += 1

        if uv_dict_by_idx:
            self._reader.save_as(outputfile, uv_dict_by_idx, verbose)
        else:
            self._reader.save_as(outputfile, None, verbose)

    def listobs(self, sids=None):
        return self._reader.listobs(sids)


class IdiHDUCardList(UserList):
    def __getitem__(self, key):
        if isinstance(key, str):
            search_key = key.upper()
            for card in self.data:
                if card["key"] == search_key:
                    return card["value"]
            raise KeyError(f"Keyword '{key}' not found.")

        return self.data[key]

    def __contains__(self, key):
        if isinstance(key, str):
            search_key = key.upper()
            for card in self.data:
                if card["key"] == search_key:
                    return True
            return False

        if isinstance(key, int):
            return 0 <= key < len(self.data)

    def __setitem__(self, key, value):
        if isinstance(key, str):
            search_key = key.upper()
            for card in self.data:
                comm = card.get("comment", "")
                if card["key"] == search_key:
                    if len(value) > 1:
                        comm = value[1]
                        value = value[0]
                    card["value"] = value
                    card["comment"] = comm
                    return
            raise KeyError(
                f"Keyword '{key}' does not exist. Use a dedicated 'add_key' method for new cards."
            )
        else:
            super().__setitem__(key, value)

    def get_dtype(self, key, default=C):
        search_key = key.upper()
        for card in self.data:
            if card["key"] == search_key:
                return card["dtype"]
        return default

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def _add_key(
        self,
        key: str,
        value: Any,
        dtype: int,
        comment: str = "",
        position: int = None,
        after: str = None,
    ):
        """
        Appends or inserts a new card. Raises if key already exists.
        position : 0-based index to insert before
        after    : insert after a named keyword (takes priority over position)
        """
        search_key = key.upper()
        for card in self.data:
            if card["key"] == search_key:
                raise KeyError(
                    f"Keyword '{search_key}' already exists. Use update_key to modify it."
                )

        new_card = {
            "key": search_key,
            "value": value,
            "comment": comment,
            "dtype": dtype,
        }

        if after is not None:
            after_key = after.upper()
            for i, card in enumerate(self.data):
                if card["key"] == after_key:
                    self.data.insert(i + 1, new_card)
                    return
            raise KeyError(f"Anchor keyword '{after_key}' not found for insertion.")

        if position is not None:
            self.data.insert(position, new_card)
        else:
            self.data.append(new_card)

    def keys(self):
        return [card["key"] for card in self.data]

    def values(self):
        return [card["value"] for card in self.data]

    def dtype_items(self):
        return [(card["key"], card["dtype"]) for card in self.data]

    def items(self):
        return [(card["key"], card["value"]) for card in self.data]

    def __repr__(self):
        reprout = f""
        for card in self.data:
            reprout += f"{card['key']:8} = {card['value']}\n"
        return f"{reprout}"


class IdiHeaderHDUList(UserList):
    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(key)

        if isinstance(key, str):
            for hdu in self.data:
                extname = getattr(hdu, "EXTNAME", None)
                if extname == key:
                    return hdu

                if key.upper() == "PRIMARY" and getattr(hdu, "is_primary", False):
                    return hdu

            raise KeyError(f"HDU '{key}' not found in file.")

        return super().__getitem__(key)

    def __repr__(self):
        summary = [f"\n{' No.':4} {'   Name':20} {'  type':15}  {'cards':6} dim"]
        summary += [f"\n{i:4} {h.summary}" for i, h in enumerate(self.data)]
        return f"<HDUList: {''.join(summary)}\n>"


class IdiHDUList(UserList):
    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(key)

        if isinstance(key, str):
            for hdu in self.data:
                extname = getattr(hdu._header_data, "EXTNAME", None)
                if extname == key:
                    return hdu

                if key.upper() == "PRIMARY" and getattr(hdu, "is_primary", False):
                    return hdu

            raise KeyError(f"HDU '{key}' not found in file.")

        return super().__getitem__(key)

    @property
    def names(self):
        return [hdu.extname for hdu in self.data]

    @property
    def summary(self):
        lines = [f"{'No.':<4} {'Name':<25} {'Type':<15} {'dim':<6}"]
        lines.append("-" * 54)

        for i, hdu in enumerate(self.data):
            name = hdu.extension_name if not hdu.is_primary else "PRIMARY"
            etype = hdu.extension_type

            rows = len(hdu.df) if hdu.df is not None else 0
            cols = len(hdu.df.columns) if hdu.df is not None else 0

            lines.append(f"{i:<4} {name:<25} {etype:<15} {str((rows, cols)):<6}")

        return "\n".join(lines)

    def __delitem__(self, index):

        # if isinstance(index, str):
        #     warn(f"HDU index number was not used!", stacklevel=2, category=UserWarning)
        hdu_to_remove = self[index]
        hdu_num = hdu_to_remove.hdu_num
        hdu_to_remove._reader.delete_hdu(hdu_num)
        super().__delitem__(hdu_num)

        for i, hdu in enumerate(self):
            hdu.hdu_num = i

    def __repr__(self):
        return self.summary


class IdIHDU:
    def __init__(
        self, header_data, table_data=None, hdu_num=None, reader=None, parent=None
    ):

        self._header_data = header_data
        self.header_data = header_data
        self.header = header_data.cards
        self.history = header_data.history
        self.comments = header_data.comments
        self._reader = reader
        self.hdu_num = hdu_num
        self._staged_hdudata = {}
        self._staged_header = {}
        self._staged_table = {}
        self._parent = parent
        self._is_modified = None
        self._staged_new_header = {}  # (value, comment, position, after)
        for attr in dir(header_data):
            if not attr.startswith("_"):
                value = getattr(header_data, attr)
                if not callable(value):
                    setattr(self.header, attr, value)

        self._table_data = table_data

        self._df = None

        self.extname = getattr(header_data, "EXTNAME", None)
        self.is_primary = getattr(header_data, "is_primary", False)
        if self.extname is None and self.is_primary:
            self.extname = "PRIMARY"
        self.dim = getattr(header_data, "dim", (0, 0))
        self.extension_type = getattr(header_data, "extension_type", "")
        self.extension_name = self.extname

    def update_col_name(self, col_name: str, new_name: str):
        """
        Renames a column by finding its TTYPE key and staging a header update.
        """
        col_name_upper = col_name.upper()
        found_key = None

        for card in self.header.data:
            if (
                card["key"].startswith("TTYPE")
                and card["value"].upper() == col_name_upper
            ):
                found_key = card["key"]
                break

        if not found_key:
            raise KeyError(f"Column '{col_name}' not found in HDU {self.name}")

        self.header[found_key] = (new_name.upper(), "")

        if col_name_upper in self._staged_table:
            self._staged_table[new_name.upper()] = self._staged_table.pop(
                col_name_upper
            )

    def update_key(self, key: str, new_value: Any, comment: str = ""):
        """
        stages header update in memory.
        """
        self._staged_header[key] = (new_value, comment)
        self.header[key] = (new_value, comment)

    def __setitem__(self, colname, value):
        """
        stages changes in memory.
        """

        current_data = self._table_data[colname]
        target_len = len(current_data)

        if not isinstance(value, (list, tuple)) and hasattr(current_data, "__len__"):
            processed_value = [value] * target_len
        else:
            processed_value = value
        self._table_data[colname][:] = processed_value
        self._staged_hdudata[colname] = processed_value

        # print("use .update() to write to disk.")

    def filter_inplace(self, mask):
        """Filters the internal table data using a boolean mask.
        example:

        rm_rows = np.isin(np.array(hdul[hdu_name]['ANNAME'])[:], [an])
        rm_rows = np.array([True, False, True, True, False])
        hdul[hdu_name].filter_inplace(~rm_rows)
        """
        self._tb_data = self.df.filter(mask).to_dict(as_series=False)
        if len(~mask) > 0:
            new_naxis2 = self.nrows - sum(~mask)
            self.update_key("NAXIS2", new_naxis2)

        self._staged_hdudata = self.df.filter(mask).to_dict(as_series=False)
        print("use .update() to write to disk.")

    def update_cell(self, colname: str, idx: int, value):
        col = self._table_data[colname]
        col[idx] = value
        self._staged_hdudata[colname] = col

    def update(self):
        if not (self._staged_hdudata or self._staged_header or self._staged_new_header):
            print("no changes to update.")
            return

        if self._staged_hdudata:
            for colname, value in self._staged_hdudata.items():
                self._reader.write_table_column(
                    hdu_num=self.hdu_num, colname=colname, data=value, start_row=0
                )
            self._staged_hdudata.clear()

        if self._staged_header:
            for key, (new_value, comment) in self._staged_header.items():
                dtype_code = self.header.get_dtype(key, C)
                if dtype_code == I:
                    self._reader.update_header_int(
                        self.hdu_num, key, int(new_value), comment
                    )
                elif dtype_code == F:
                    self._reader.update_header_double(
                        self.hdu_num, key, float(new_value), comment
                    )
                elif dtype_code == L:
                    val = 1 if str(new_value).upper() in ["T", "TRUE", "1"] else 0
                    self._reader.update_header_int(self.hdu_num, key, val, comment)
                else:
                    self._reader.update_header_str(
                        self.hdu_num, key, str(new_value), comment
                    )
            self._staged_header.clear()

        if self._staged_new_header:
            for key, (
                str_value,
                comment,
                position,
                after,
                dtype,
            ) in self._staged_new_header.items():
                if after is not None:
                    self._reader.insert_header_after(
                        self.hdu_num, after, key, str_value, comment, dtype
                    )
                elif position is not None:
                    self._reader.insert_header(
                        self.hdu_num, position, key, str_value, comment, dtype
                    )
                else:
                    # Append at end - use add methods
                    if dtype == I:
                        self._reader.add_header_int(
                            self.hdu_num, key, int(str_value), comment
                        )
                    elif dtype == F:
                        self._reader.add_header_double(
                            self.hdu_num, key, float(str_value), comment
                        )
                    elif dtype == L:
                        self._reader.add_header_int(
                            self.hdu_num, key, 1 if str_value == "T" else 0, comment
                        )
                    else:
                        self._reader.add_header_str(
                            self.hdu_num, key, str_value, comment
                        )

            self._staged_new_header.clear()

    def _infer_dtype(self, value: Any) -> int:
        if isinstance(value, bool):
            return L
        if isinstance(value, int):
            return I
        if isinstance(value, float):
            return F
        return C

    def add_key(
        self,
        key: str,
        new_value: Any,
        dtype: int = None,
        comment: str = "",
        position: int = None,
        after: str = None,
    ):
        """
        Stages a new header card for insertion.

        Args:
            key: Keyword name
            new_value: Value to store
            dtype: FITS type code (I, F, C, L from FITS_TYPE_MAP) - auto-inferred if None
            comment: Keyword comment
            position: 0-based index to insert at (converted to 1-indexed for CFITSIO)
            after: Insert after this keyword name (takes priority over position)
        """
        ukey = key.upper()
        if ukey in self._staged_header or ukey in self._staged_new_header:
            raise KeyError(
                f"Keyword '{ukey}' already exists. Use update_key to modify it."
            )

        if dtype is None:
            dtype = self._infer_dtype(new_value)

        str_value = str(new_value)
        if dtype == L:
            numeric_value = 1 if str(new_value)[0].upper() == "T" else 0
            str_value = str(numeric_value)  # Convert to string "1" or "0"

        cpp_position = position
        # if position is not None:
        #     cpp_position = position + 1  # Convert to 1-indexed for CFITSIO

        self._staged_new_header[ukey] = (str_value, comment, cpp_position, after, dtype)
        self.header._add_key(
            ukey,
            new_value,
            dtype=dtype,
            comment=comment,
            position=position,
            after=after,
        )

    def delete_key(self, key: str):
        protected = ["SIMPLE", "BITPIX", "NAXIS", "XTENSION", "PCOUNT", "GCOUNT", "END"]

        if key in protected:
            raise ValueError(f"{key} is a mandatory FITS keyword. ")
        else:
            if key in self.header.keys():
                self._reader.delete_header_key(self.hdu_num, key)
                if hasattr(self, key):
                    delattr(self, key)

                for i, card in enumerate(self.header):
                    if card.get("key") == key:
                        self.header.pop(i)
                        break
                return True
            else:
                raise KeyError(f"{key}")

    @property
    def nrows(self):
        return self.dim[0]

    @property
    def df(self):
        if self._df is None and self._table_data is not None:
            self._df = pl.from_dict(self._table_data)
        return self._df

    @property
    def cols(self):
        return list(self._table_data.keys()) if self._table_data is not None else None

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._table_data[key]

    def __contains__(self, key):
        if isinstance(key, str):
            return key in self._table_data
        if isinstance(key, int):
            return 0 <= key < len(self._table_data)

    def __repr__(self):
        return str(self.df)


class IdiHeaderManagerBase(type):
    def __new__(mcs, name, bases, attrs):
        local_props = {k for k, v in attrs.items() if isinstance(v, property)}

        def get_data(self):
            card_list = IdiHDUCardList()
            combined_attrs = {**type(self).__dict__, **self.__dict__}
            allignore_keys = CLASS_ATTRS | local_props

            for _key, _value in combined_attrs.items():
                if not _key.startswith("_") and _key not in allignore_keys:
                    value = getattr(self, _key)
                    if not callable(value):
                        dtype = self._dtypes.get(_key, 16)
                        card_list.append({"key": _key, "value": value, "dtype": dtype})
            return card_list

        attrs["cards"] = property(get_data)
        return super().__new__(mcs, name, bases, attrs)


class IdiHeaderManager(metaclass=IdiHeaderManagerBase):
    """to collect the C++ HeaderManager objects into IdiHDUHeader

    Args:
        metaclass (_type_, optional): _description_. Defaults to IdiHeaderManagerBase.
    """

    def __init__(
        self,
        history: Optional[List[str]] = None,
        comments: Optional[List[str]] = None,
        dtypes: Optional[Dict[str, int]] = None,
        **kwargs,
    ) -> None:

        self._history: List[str] = history or []
        self._comments: List[str] = comments or []
        self._dtypes: Dict[str, int] = dtypes or {}

        for key, value in kwargs.items():
            if isinstance(value, str):
                value = value.strip("' ").strip()
            setattr(self, key, value)

    @property
    def cards(self) -> List[HeaderCardDict]: ...

    @property
    def history(self):
        return self._history

    @property
    def comments(self):
        return self._comments


class IdiHDUHeader(IdiHeaderManager):
    """Reads header for the provided HDU
        NOTE: Only reads the raw header written on the FITS file, without modifying or appending any cards.
        e.g might be missing : SIMPLE for Primary and RDATE for Binary tables when not available in the headers.

    Returns:
        IdiHDUHeader
    """

    @property
    def is_primary(self):
        return hasattr(self, "SIMPLE") and not hasattr(self, "XTENSION")

    @property
    def is_idihdu(self):
        has_groups = str(getattr(self, "GROUPS", "F")).upper().startswith("T")
        naxis_is_zero = int(getattr(self, "NAXIS", -1)) == 0
        return self.is_primary and has_groups and naxis_is_zero

    @property
    def extension_type(self):
        return getattr(self, "XTENSION", "PRIMARY")

    @property
    def extension_name(self):
        return getattr(self, "EXTNAME", self.extension_type)

    @property
    def hdu_type(self):
        return "IdiHDU" if self.is_primary else "Idi" + self.extension_type

    @property
    def dim(self):
        ncols = int(getattr(self, "TFIELDS", 0))
        nrows = int(getattr(self, "NAXIS2", 0))
        return (nrows, ncols)

    @property
    def ncards(self):
        return len(self.cards) + len(self.history) + len(self.comments)

    @property
    def summary(self):
        return f"{self.extension_name:20} {self.hdu_type:15} {self.ncards:6} ({self.dim[0]}R,{self.dim[1]}C)"

    def __repr__(self):
        return self.summary
