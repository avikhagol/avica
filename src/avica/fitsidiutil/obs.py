from astropy.time import Time
import polars as pl
from avica.fitsidiutil.io import FITSIDI
import numpy as np
from itertools import count
from .op import get_yyyymmdd

from typing import List
from dataclasses import dataclass, field


# -------------------------------------------------------------

pl.Config(
            ascii_tables                =   True,       # Use +--+ instead of Unicode boxes
            tbl_hide_column_data_types  =   True,
            tbl_hide_dataframe_shape    =   True,
            tbl_width_chars             =   10000,
            float_precision             =   4,
            tbl_rows                    =   -1,
            tbl_cols                    =   -1
            )

# -------------------------------------------------------------

class ListObs:
    def __init__(self, fitsfilepath, sids=None, time_scale_data='tai', scangap=15, scale_dateobs='utc'):
        self.fitsfilepath                               =   fitsfilepath
        self.time_scale_data                            =   time_scale_data
        self.scale_dateobs                              =   scale_dateobs
        self.scangap                                    =   scangap

        self.scanlist                                   =   []

        self.sids                                       =   [int(s) for s in sids] if sids else None

        self.df_listobs                                 =   self.summary()

    def _get_colnames(self, hdu, cols):
        matching_cols = []
        found_cols = hdu.cols

        for col in cols:
            matching_cols += [colname for colname in found_cols if col in colname]

        return matching_cols

    def summary(self,):
        """get the summary of the observation from the FITSIDI file

        Returns:
            :df_listobs:        (pandas.DataFrame)
                                summary of the observation with columns: start_time, end_time, sid, nrows, inttime, source
        """
        fo              =   FITSIDI(self.fitsfilepath)
        fo.open()
        hdul            =   fo.read(max_chunk=100)
        dateobs         =   hdul[0].header['DATE-OBS']
        yyyy,mm,dd         =   get_yyyymmdd(dateobs=dateobs)
        dateobs         =   f"{yyyy}-{mm:02}-{dd:02}"

        dateobs         =   Time(dateobs, format='isot', scale=self.scale_dateobs)
        rowd            =   fo.listobs(sids=self.sids)
        hdu_source             =   fo.hdul['SOURCE']
        sid_colname     =   self._get_colnames(hdu_source, ['ID_NO', 'SOURCE_ID'])[0]

        sids = [int(sid) for sid in hdu_source[sid_colname]]

        stargets = [str(src) for src in hdu_source['SOURCE']]
        dic_sources = dict(zip(sids,stargets))

        self.dic_sources    =   dic_sources
        fo.close()

        prev_end_mjd = Time(0, format='mjd', scale=self.time_scale_data)

        row_idx = 0
        dict_listobs = {}

        for row in rowd:
            time_start_mjd = Time(row.time_start + dateobs.mjd, format='mjd', scale='tai')
            time_end_mjd = Time(row.time_end + dateobs.mjd, format='mjd', scale='tai')

            if (time_end_mjd - prev_end_mjd).sec >= self.scangap:

                inttime_rounded = np.round(np.array(row.inttime), 3).tolist()

                dict_listobs[row_idx] = {
                    'scan': row_idx+1,
                    'start_time': time_start_mjd.isot,
                    'end_time': time_end_mjd.isot,
                    'source_id': row.source,
                    'nrows': row.nrows,
                    'inttime': inttime_rounded
                }
                self.scanlist.append(row.source)
                row_idx += 1

            prev_end_mjd = time_end_mjd

        self.dict_listobs = dict_listobs
        df_listobs = pl.from_dicts(list(dict_listobs.values()))

        if not df_listobs.is_empty():
            df_listobs = df_listobs.with_columns([
                pl.col("start_time").str.to_datetime(),
                pl.col("end_time").str.to_datetime()
            ])


        df_listobs = df_listobs.with_columns(
            pl.col("source_id").cast(pl.String).replace(dic_sources).alias("source")
        )

        cols = df_listobs.columns
        cols.remove("source")
        cols.insert(3, "source")
        df_listobs = df_listobs.select(cols)
        return df_listobs

def merge_and_reorder(base_dict, *new_dicts):
    seen_obs = set()
    pairs = []

    additional_dicts = [d for d in new_dicts if d]
    is_merge = len(additional_dicts) > 0

    for d in filter(None, [base_dict, *new_dicts]):
        lookup = {str(k): v for k, v in d.get('sources', {}).items()}
        for obs in d.get('listobs', {}).values():
            key = (obs.get('start_time'), obs.get('end_time'))
            if key in seen_obs:
                continue
            seen_obs.add(key)

            old_id = str(obs.get('sid') or obs.get('source_id'))
            pairs.append((obs, lookup.get(old_id, 'Unknown')))
    if is_merge:
        pairs.sort(key=lambda x: x[0].get('start_time', '9999'))

    name_to_id = {}
    final_sources = {}
    final_listobs = {}
    id_counter = count(1)

    for i, (obs, source_name) in enumerate(pairs):
        if source_name not in name_to_id:
            new_id = next(id_counter)
            name_to_id[source_name] = new_id
            final_sources[str(new_id)] = source_name

        new_scan = i + 1
        final_listobs[str(i)] = {
            **{k: v for k, v in obs.items() if k not in ('sid', 'source_id', 'scan')},
            'scan': new_scan,
            'source_id': name_to_id[source_name],
        }

    return {
        'scanlist': list(range(1, len(final_listobs) + 1)),
        'listobs': final_listobs,
        'sources': final_sources,
    }

@dataclass
class ObservationSummary:
    """_summary_

    Args:
        fitsfilepaths (list, required): _description_. Defaults to [].
    """
    fitsfilepaths:List
    sids:List = field(default_factory=list)
    scangap=15
    dic_summary : dict = field(default_factory=dict)



    def get(self,):
        dic_list =[]
        if isinstance(self.fitsfilepaths, str):
            self.fitsfilepaths = [self.fitsfilepaths]
        for fitsfile in self.fitsfilepaths:
            listobs_data = ListObs(fitsfilepath=fitsfile, sids=self.sids, scangap=self.scangap)
            dic_new = {"scanlist": listobs_data.scanlist,
                        "listobs": listobs_data.dict_listobs,
                        "sources": listobs_data.dic_sources,
                        }
            dic_list.append(dic_new)
            self.dic_summary = merge_and_reorder(*dic_list)
        self

    def to_polars(self):
        if not self.dic_summary:
            self.get()
        df_listobs = pl.DataFrame(list(self.dic_summary['listobs'].values()))
        if not df_listobs.is_empty():
            df_listobs = df_listobs.with_columns([
                pl.col("start_time").str.to_datetime(),
                pl.col("end_time").str.to_datetime()
            ])

        dic_sources = self.dic_summary['sources']
        df_listobs = df_listobs.with_columns(
            pl.col("source_id").cast(pl.String).replace(dic_sources).alias("source")
        )

        cols = df_listobs.columns
        cols.remove("source")
        cols.insert(3, "source")
        df_listobs = df_listobs.select(cols)
        return df_listobs

    def scanlist(self):
        if not self.dic_summary:
            self.get()
        return self.dic_summary['scanlist']
