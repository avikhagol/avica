from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, List
from collections import UserList
from typing import NamedTuple
import inspect
import polars as pl
import numpy as np
import subprocess
from collections import Counter
from pathlib import Path
from .op import get_yyyymmdd, _getcolname, _gethduname
from .io import FITSIDI

import warnings

@dataclass
class ValidationResult:
    code            : str
    hdu             : str
    key             : str
    msg             : str       =   ''
    fixed           : bool      =   False
    need_fixing     : bool      =   False
    detail          : str       =   ""
    bad_data        : List[Any] =   field(default_factory=list)

code_desc = {
        'binary'                    :   "binary data found in table values",
        'extra_byte'                  :   "extra byte found due to padding",
        'empty'                     :   "empty values found",
        'date'                      :   "date format wrong",
        'duplicate'                :   "dulicate entries in data",
        'zeros'                     :   "leading zeros in digit like source name",
        'multifreqid'               :   "multiple freqid present",
        'anmap'                     :   "antenna mapping wrong",
        'array'                     :   "column array doesnt exist",
        'col_spell'                  :   "column spelled wrong",
        "primary"                   :   "primary header check for fitsidi standards"
    }

class IdiValidatorBase(ABC):
    code    : str
    run_once: bool = False
    scope   : str  = 'columns'   # 'data' | 'header' | 'columns'
    
    @abstractmethod
    def check(self, hdu_name: str, key: str, hdu_data) -> List[ValidationResult]: 
        col_name = key
        """check if problems. Returns [] if None."""
    
    @abstractmethod    
    def fix(self, hdu_name: str, key: str, result: ValidationResult) -> bool:
        col_name = key
        """attempt fix. Return True if success."""
        
    def desc(self):
        return code_desc.get(self.code, self.code)
    
    def result(self, hdu: str, col: str, msg: str, **kwargs) -> ValidationResult:
        """Helper to create a ValidationResult with the current validator's code."""
        return ValidationResult(code=self.code,hdu=hdu,key=col,msg=msg,**kwargs)
    
    def bin_to_str(self, s):
        return str(s).split('\\')[0].replace("b'", "")



class ValidationReport(UserList[ValidationResult]):
    """A collection of ValidationResults with export capabilities."""
    
    def to_polars(self) -> pl.DataFrame:
        if not self.data:
            return pl.DataFrame()
        dicts = []
        for r in self.data:
            d = asdict(r)
            if isinstance(d.get('detail'), (list, dict)):
                d['detail'] = str(d['detail'])
            dicts.append(d)
        return pl.DataFrame(dicts)

    def summary(self):
        """Prints a quick summary count of issues vs fixed."""
        df = self.to_polars()
        if df.is_empty():
            return "No issues found."
        return df.group_by('hdu').agg(
            fixable=pl.col('need_fixing').sum(),
            total = pl.len(),
            fixed=pl.col("fixed").sum(),
            problem_code=pl.col('code').filter(pl.col('need_fixing')).unique(),
            affected=pl.col('key').filter(pl.col('need_fixing')).unique()
        )
    
    def __repr__(self):
        return str(self.summary())

class AntennaNameMappingValidator(IdiValidatorBase):
    code = "anmap"
    
    anidcols = ['ANTS', 'ANTENNA_NO']
    
    def check_missing_ant(self, hdul, table_name, col):
        """returns index where the ants is missing"""
        
        set_flag = set()
        rm_rows = []
        affected_data = []
        multidimcol = len(np.shape(hdul[table_name][col]))>1
        if multidimcol:
            set_flag.update([an for an in np.array(hdul[table_name][col])[:,0]])
        else:
            set_flag.update([an for an in np.array(hdul[table_name][col])])

        for an in set_flag:
            anname_data = hdul['ANTENNA']['ANNAME']
            anno_data = hdul['ANTENNA']['ANTENNA_NO']
            if not sum(np.isin(np.array(anno_data), [an])):
                affected_data.append(an)
                if multidimcol:
                    rm_rows.append(np.isin(np.array(anname_data)[:,0], [an]))
                else:
                    rm_rows.append(np.isin(np.array(anname_data)[:], [an]))
        return rm_rows, affected_data    
    
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, **kwargs)        
        if hdu_name not in hdul.names:return result(msg='hdu not present', key=key, need_fixing=False)
        if key not in self.anidcols:return result(msg='skipped', key=key, need_fixing=False)
        affected_data =   []
        
        missing_ants_location, affected_data = self.check_missing_ant(hdul, hdu_name, key)
        
        return result(msg=f"{self.desc()}", need_fixing=sum(missing_ants_location)>0, detail=missing_ants_location, bad_data=affected_data, key=hdu_name)
    
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
    
        rm_rows_list             =   result.detail
        for rm_rows in rm_rows_list:
            hdul['ANTENNA'].filter_inplace(~rm_rows)
        hdul[hdu_name].update()
        result.fixed = True
        return result.fixed

class BinaryColDataValidator(IdiValidatorBase):
    code = "binary"
    
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        col_name = key
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, key=col_name, **kwargs)
        
        if hdu_name not in hdul.names:return result(msg='hdu not present', need_fixing=False)

        for colname_inidihdu in hdul[hdu_name].cols:
            if col_name == colname_inidihdu:
                if any('\\' in str(colvalue) for colvalue in hdul[hdu_name][col_name]):
                    return result(msg=f"{self.desc()}",need_fixing=True, bad_data=hdul[hdu_name][col_name])

        return result(msg='col not present', need_fixing=False)
    
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
        col_name = key
        hdul[hdu_name][col_name] = [self.bin_to_str(colvalue) for colvalue in hdul[hdu_name][col_name]]
        hdul[hdu_name].update()
        result.fixed = True
        return result.fixed
    
class BoilerPlateValidator(IdiValidatorBase):
    code = "boilerplate"
    
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        col_name = key
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, key=col_name, **kwargs)
        bad_data = []
        if hdu_name not in hdul.names:return result(msg='hdu not present', need_fixing=False)

        ...

        return result(msg=f"{self.desc()}", need_fixing=len(bad_data)>0, detail=bad_data, bad_data=bad_data, key=",".join(bad_data))
    
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
        col_name = key
        ...
        result.fixed = True
        return result.fixed
    

class ColumnNameValidator(IdiValidatorBase):
    code = "col_spell"
    
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        col_name = key
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, key=col_name, **kwargs)
        
        if hdu_name not in hdul.names:return result(msg='hdu not present', need_fixing=False)

        for colname_inhdul in hdul[hdu_name].cols:
            if (col_name != colname_inhdul) and (set(colname_inhdul.replace(' ','').replace('.','').replace('_','')) ==set(col_name.replace('_',''))):
                return result(msg=f"{colname_inhdul}-->{col_name} in {hdu_name}",need_fixing=True, bad_data=colname_inhdul)

        return result(msg='col not present', need_fixing=False)
    
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
        col_name = key
        hdul[hdu_name].update_col_name(result.bad_data, col_name)
        hdul[hdu_name].update()
        result.fixed = True
        return result.fixed


class DuplicateValueValidator(IdiValidatorBase):
    code = "duplicate"
    scope = "data"
    
    duplicate_hdu = {'SOURCE': {'SOURCE':['SOURCE_ID', 'ID_NO.', 'ID_NO'], },
                     }
    
    def choose_correct_id_forduplicate_fields(self, hdu, verbose=False, scanlist=[], size_chunk=50_000):
        list_chosen_ids, list_dupl_ids, list_rejected_ids = [], [], []
        fop                      =   FITSIDI(hdu.filename)
        
        shdu, shduids           = _gethduname(hdu, ['SOURCE'])
        source_data             =   hdu[shdu]
        source_col              = _getcolname(source_data,['SOURCE'])
        id_col                  = _getcolname(source_data,['SOURCE_ID', 'ID_NO.', 'ID_NO'])
        
        
        def get_source_id_in_uvd(fo, total_rows, size_chunk):
            hdugen =fo.iter_read(total_rows, size_chunk=size_chunk)
            source_id_uvdata = set()
            for i, hdul in enumerate(hdugen):
                found_in_chunk = (
                    hdul['UV_DATA'].df
                        .select('SOURCE')
                        .unique()
                        .to_series()
                        .to_list()
                    )
                
                source_id_uvdata.update(found_in_chunk)
                if verbose: print(f"chunk {i+1}: {set(found_in_chunk)} sources found")
            return source_id_uvdata

        snames = list(hdu[shdu][source_col])

        if len(snames)!=len(np.unique(snames)):
            duplicates          =   [k for k,v in Counter(snames).items() if v>1]
            total_rows          =   hdu['UV_DATA'].nrows
            
            for duplicate_source in duplicates:
                subset = source_data.df.filter(pl.col(source_col) == duplicate_source)
                
                differing_cols = [
                    col for col in subset.columns 
                    if (subset[col].round(6).n_unique() > 1 
                        if subset[col].dtype in [pl.Float32, pl.Float64] 
                        else subset[col].n_unique() > 1)
                ]
                
                duplicate_ids       =   hdu[shdu].df.filter(pl.col(source_col)==duplicate_source)[id_col].to_list()
                if differing_cols != [id_col]: # TODO: add way to replace the source name with the provided one, chosen id can be used to select the source name.
                    print(f"sources {duplicate_ids} in SOURCE tablle have different columns for {differing_cols}")
                list_dupl_ids.extend(duplicate_ids)

            
            if len(list_dupl_ids):
                if not len(scanlist):
                    source_id_uvdata = get_source_id_in_uvd(fop, total_rows, size_chunk)
                else:
                    source_id_uvdata = list(set(scanlist))
                
                for dupl_id in list_dupl_ids:
                    if dupl_id in source_id_uvdata:
                        list_chosen_ids.append(dupl_id)
                    else:
                        list_rejected_ids.append(dupl_id)
                        
        return list_chosen_ids, list_rejected_ids
    
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        col_name = key
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, **kwargs)
        
        if hdu_name not in list(self.duplicate_hdu.keys()):return result(msg='skipped', key=col_name, need_fixing=False)
        
        duplicates = []
        for hdu_name_check, dict_colname in self.duplicate_hdu.items():
            
            for possible_colname, possible_idcolname in dict_colname.items():
                shdu, shduids           = _gethduname(hdul, [hdu_name_check])
                if not shdu:
                    warnings.warn(("SOURCE table not found."), UserWarning, stacklevel=2)
                source_data             =   hdul[shdu]
                source_col              = _getcolname(source_data,[possible_colname])
                id_col                  = _getcolname(source_data,possible_idcolname)
                snames                  = hdul[shdu][source_col]
                
                if len(snames)!=len(np.unique(snames)):
                    duplicates          =   [k for k,v in Counter(snames).items() if v>1]        

        return result(msg=f"{self.desc()}", need_fixing=len(duplicates)>0, detail=[id_col], bad_data=duplicates, key=",".join(duplicates))
    
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult, scanlist=[]) -> bool:
        chosen_id, rm_ids = self.choose_correct_id_forduplicate_fields(hdul, verbose=True, size_chunk=50_000, scanlist=scanlist)
        id_col = result.detail[0]
        rm_rows = np.isin(np.array(hdul[hdu_name][id_col])[:], rm_ids)
        
        hdul[hdu_name].filter_inplace(~rm_rows)
        hdul[hdu_name].update()
        result.fixed = True
        return result.fixed
   
    
class EmptyColDataValidator(IdiValidatorBase):
    code = "empty"
    
    def temp_solution_poltya(self, hdul, hdu_name, col_name, target_name=''):
        poltya = []
        if hdu_name in hdul.names:
            if 'POLTYA' in col_name:
                poltya = hdul[hdu_name][col_name]
                if target_name:
                    from vasco.helpers import query_vlba
                    tbres                   =   query_vlba(str(hdul[0].header['OBSERVER']).strip(),Path(hdul.filename()).stem,target_name)[0]['pol_states']
                    # print(hdul[hdu_name][col_name].astype(str), hdul[hdu_name][col_name].dtype)
                    if 'LL' in tbres:
                            poltya =   ['L']*len(poltya)
                    elif 'RR' in tbres:
                            poltya =   ['R']*len(poltya)
                if len(poltya):
                    if 'POLTYB' in hdul[hdu_name].cols:
                        poltya = ['R']*len(poltya) if 'L' in hdul[hdu_name]['POLTYB'] else ['L']*len(poltya)
                    else:
                        poltya = ['R']*len(poltya)
                    hdul[hdu_name][col_name] =     poltya
            elif 'POLTYB' in col_name:
                poltyb = hdul[hdu_name][col_name]
                if 'POLTYA' in hdul[hdu_name].cols:
                    poltyb = ['R']*len(poltyb) if 'L' in hdul[hdu_name]['POLTYA'] else ['L']*len(poltyb)
                else:
                    poltyb = ['R']*len(poltya)
                hdul[hdu_name][col_name] =   poltyb
            hdul[hdu_name].update()
    
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        col_name = key
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, key=col_name, **kwargs)
        
        if hdu_name not in hdul.names:return result(msg='hdu not present', need_fixing=False)

        for colname_inhdul in hdul[hdu_name].cols:
            if col_name == colname_inhdul:
                if any(''==str(colvalue) for colvalue in hdul[hdu_name][col_name]):
                    return result(msg=f"{self.desc()}",need_fixing=True, bad_data=hdul[hdu_name][col_name])

        return result(msg='col not present', need_fixing=False)
    
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
        col_name = key
        self.temp_solution_poltya(hdul, hdu_name, col_name, target_name='')     # FIXME : current solution does not retrieve the observation setup from NRAO or user.
        result.fixed = True
        return result.fixed
    

class ExtraByteValidator(IdiValidatorBase):
    code = "extra_byte"
    run_once = True
    scope = "header"
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        col_name = key
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, key=col_name, **kwargs)
        if hdul.extra_byte_location is not None:
            return result(msg=str(hdul.extra_byte_location), need_fixing=True)
            
        return result(msg='', need_fixing=False)
    
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
        subprocess.run(['truncate', '-s', str(hdul.extra_byte_location), hdul.filename])
        result.fixed = True
        return result.fixed


class HeaderDateValidator(IdiValidatorBase):
    code    = "date"
    scope   = "header"
    
    date_card = ['DATE-OBS', 'RDATE', 'DATE-MAP']
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, **kwargs)
        if hdu_name not in hdul.names:return result(msg='header not present', key=key, need_fixing=False)
        
        affected_cols, bad_date, correct_date = [], [],{}
        for date_key in self.date_card:
            if date_key in hdul[hdu_name].header:
                date_found  = str(hdul[hdu_name].header[date_key])
                yyyy,mm,dd  = get_yyyymmdd(dateobs=date_found)
                corrected_date = f"{yyyy}-{mm:02}-{dd:02}"
                
                if date_found!=corrected_date:
                    bad_date.append(date_found)
                    correct_date[date_key]=corrected_date
                    affected_cols.append(date_key)
            
        return result(msg=f"{self.desc()}", need_fixing=len(correct_date)>0, detail=[correct_date], bad_data=bad_date, key=",".join(affected_cols))
        
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
        date_dict_corrected = result.detail[0]
        for key_date, new_val in date_dict_corrected.items():
            hdul[hdu_name].update_key(key_date, new_val)
        hdul[hdu_name].update()
        result.fixed = True
        return result.fixed

class HeaderPrimaryValidator(IdiValidatorBase):
    code = "primary"
    scope = "header"
    run_once = True
    
    mandatory_header = {'NAXIS':0, 'EXTEND':True}
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, **kwargs)
        if hdu_name not in ['PRIMARY']:return result(msg='header not present', key=key, need_fixing=False)
        
        affected_keys, bad_data, corrected_data = [], [],[]
        for key, v in self.mandatory_header.items():
            if key not in hdul[hdu_name].header:
                affected_keys.append(key)
                bad_data.append('')
                corrected_data.append({key:v})
            else:
                if str(hdul[hdu_name].header[key]) != str(v):
                    affected_keys.append(key)
                    bad_data.append(key)
                    corrected_data.append({key:v})
            
        return result(msg=f"{self.desc()}", need_fixing=len(corrected_data)>0, detail=corrected_data, bad_data=bad_data, key=",".join(affected_keys))
        
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
        for i, dict_corrected in enumerate(result.detail):
            for key, new_val in dict_corrected.items():
                if result.bad_data[i]=='':
                    warnings.warn((f"{key} not found: check results"), UserWarning, stacklevel=2)
                hdul[hdu_name].update_key(key, new_val)
        hdul[hdu_name].update()
        result.fixed = True
        return result.fixed

class LeadingZerosValidator(IdiValidatorBase):
    code = "zeros"
    scope = "data"
    hdu_names = ['SOURCE']
    
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, **kwargs)        
        if hdu_name not in self.hdu_names:return result(msg='skipped', key=key, need_fixing=False)
        
        affected_data,corrected_data,bad_data =   [],{},[]
        for i,src in enumerate(hdul[hdu_name]['SOURCE']):
            if str(src)[0] == '0':
                isint = False
                try:
                    _ = int(src)
                    isint = True
                except Exception:
                    isint = False
                if isint:
                    affected_data.append(src)
                    bad_data.append(src)
                    corrected_data[i]=[('O' * (len(src) - len(src.lstrip('0'))) + src.lstrip('0')) if src.lstrip('0').isdigit() else src][0]
        return result(msg=f"{self.desc()}", need_fixing=len(bad_data)>0, detail=corrected_data, bad_data=bad_data, key=",".join(affected_data))
    
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
        print(result.detail)
        for idx, corrected_data in result.detail.items():
            hdul[hdu_name].update_cell('SOURCE', idx, corrected_data)
        hdul[hdu_name].update()
        result.fixed = True
        return result.fixed

class MultipleFrequencyIdValidator(IdiValidatorBase):
    code = "multifreqid"
    scope = "data"
    FREQID_CHK_COL = ['FREQUENCY', 'ANTENNA', 'GAIN_CURVE', 'SYSTEM_TEMPERATURE', 'SOURCE']
    
    def check(self, hdu_name: str, key: str, hdul) -> ValidationResult:  
        def result(**kwargs):return ValidationResult(code=self.code,hdu=hdu_name, **kwargs)        
        
        if hdu_name not in hdul:return result(msg='skipped', key=key, need_fixing=False)
        if 'FREQID' not in hdul[hdu_name]: return result(msg='missing', key='FREQID', need_fixing=True)
        if all(np.array(hdul[hdu_name]['FREQID'])==1): return result(msg='skipped', key='FREQID', need_fixing=False)
        
        return result(msg=f"{self.desc()}", need_fixing=True, detail=hdul[hdu_name]['FREQID'], bad_data=hdul[hdu_name]['FREQID'], key='FREQID')
    
    def fix(self, hdu_name: str, key: str, hdul, result: ValidationResult) -> bool:
        
        result.fixed = False    # TODO: complete me; take help from AntennaNameMapping and Duplicate validators
        return result.fixed
    
class IssueIdiHDU(NamedTuple):
    prob_class  :   str
    values      :   List

class IssueList(UserList[IssueIdiHDU]):
    def to_polars(self) -> pl.DataFrame:
        if not self.data:
            return pl.DataFrame()
        classes = []
        values = []
        
        for r in self.data:
            # for val in r.values:
            classes.append(r.prob_class)
            values.append(r.values)

        return pl.DataFrame({
            "class": classes,
            "value": values
        })
    
    def __repr__(self):
        return str(self.to_polars())


class FITSIDIValidator:
    def __init__(self, fitsfilepath: str):
        self.fitsfilepath = fitsfilepath
        self._validators: dict[str, IdiValidatorBase] = {}
        self._issues : IssueList[IssueIdiHDU] = IssueList()
        
        self.validators =  self._register_defaults()
        self.issues = self._register_issues()

    def _register_defaults(self):
        for cls in [ExtraByteValidator, ColumnNameValidator, BinaryColDataValidator, EmptyColDataValidator, 
                    DuplicateValueValidator, LeadingZerosValidator, AntennaNameMappingValidator, MultipleFrequencyIdValidator,
                    HeaderDateValidator, HeaderPrimaryValidator]:
            instance = cls()
            self._validators[instance.code] = instance
        
        return self._validators
    
    def _register_issues(self):
        for issue in [
            IssueIdiHDU('PRIMARY', ['']),
            IssueIdiHDU('SOURCE', ['SOURCE']), 
            IssueIdiHDU('ANTENNA', ['ANNAME', 'POLTYA', 'POLTYB']),
            IssueIdiHDU('FLAG', ['ANTS', 'ARRAY']), 
            IssueIdiHDU('PHASE-CAL',['ANTENNA_NO', 'ARRAY']), 
            IssueIdiHDU('UV_DATA',['ARRAY']),
            IssueIdiHDU('FREQUENCY', ['FREQID']),
            IssueIdiHDU('ARRAY_GEOMETRY', ['ANNAME']),
            IssueIdiHDU('GAIN_CURVE', ['ARRAY']),
            IssueIdiHDU('SYSTEM_TEMPERATURE', ['ARRAY'])
            ]:
            self._issues.append(issue)
        return self._issues
    
    def filter_codes(self, *keys):
        if len(keys):
            self.validators = {k: v for k, v in self._validators.items() if k in keys}
        return self

    def register_validator(self, validator: IdiValidatorBase):
        """Add or override a validator at runtime."""
        self._validators[validator.code] = validator
    
    def register_issues(self, issue: IssueIdiHDU):
        self._issues.append(issue) 
        
    def run(self, fix: bool = False, **params) -> ValidationReport[ValidationResult]:
        all_result = ValidationReport()
        fo = FITSIDI(self.fitsfilepath)
        
        with fo.open(mode='r' if not fix else 'wr') as fop:
            hdul = fop.read()
            
            ran_once = set()
            for hdu_name, columns in self._issues:
                for code, validator in self.validators.items():
                    sig = inspect.signature(validator.fix)
                    
                    validator_arg = set(sig.parameters.keys())
                    filtered_kwargs = {k: v for k, v in params.items() if k in validator_arg}

                    if validator.run_once and code in ran_once:
                        continue 
                    if (validator.scope == "header") or (validator.scope == "data"):
                        
                        results = validator.check(hdu_name, '', hdul)
                        all_result.append(results)
                        if results.need_fixing and fix:
                            validator.fix(hdu_name, '', hdul, results, **filtered_kwargs)
                            fo.flush()
                    else:
                        for column in columns:
                            if column not in ran_once:
                                results = validator.check(hdu_name, column, hdul)
                                all_result.append(results)
                                if results.need_fixing and fix:
                                    validator.fix(hdu_name, column, hdul, results)
                                    fo.flush()
                    if validator.run_once:
                        ran_once.add(code)
                            
        return all_result
    
    def validators_to_polars(self):
        validators_data = [
        {
            "code": val.code,
            "run_once": val.run_once,
            "scope": val.scope,
            "description": val.desc(),
            "class": val.__class__.__name__
        }
        for val in self.validators.values()
        ]

        validators_df = pl.DataFrame(validators_data)
        return validators_df
    
    def __repr__(self):
        return str(self.validators_to_polars())


def fitsidi_check(fitsfilepath, **kwargs):
    return FITSIDIValidator(fitsfilepath=fitsfilepath, **kwargs)
