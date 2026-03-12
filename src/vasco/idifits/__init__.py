from vasco.fits import datetimerange_fromfits, get_dateobs
from vasco.sources import check_band
from astropy.time import Time
from urllib import request

from vasco import vascodir
from pathlib import Path

from datetime import datetime, timedelta
import numpy as np


class ANTAB:
    """
    To deal with all the ANTAB related tasks.
    looks for `vlba_gains.key` file if not self.vlbagainfile
    """
    def __init__(self, fitsfile, vlbacalfile):
        self.fitsfile       =   fitsfile
        self.vlbacalfile    =   vlbacalfile
        
        self.tsystxt,_,_    =   get_tsys_txt_fromtsmcallog(vlbacalfile)
        self.vlbagainfile   =   None
        self.dateobs        =   get_dateobs(fitsfile)
        self.gainfilename   =   'vlba_gains.key'

    def make_thevlbagainfile(self):
        if not self.vlbagainfile or not Path(self.vlbagainfile).exists():
            self.vlbagainfile = str(Path(vascodir) / self.gainfilename)
        return self.vlbagainfile
    
    def get_vlbagainfile(self):
        vlbagainfile                =   self.make_thevlbagainfile()
        if not vlbagainfile or not Path(vlbagainfile).exists():
            _                       =   get_vlbagains(fl=self.gainfilename, outfile=vlbagainfile)
        return vlbagainfile

    def gen_antab(self, outfile):
        """
        TODO: if VLBA get_vlbagainfile, elif EVLA get_ygainfile, elif global get_gainlist
        """
        vlbagainfile                =   self.get_vlbagainfile()
        main_antab_txt              =   ''
        allans                      =   []

        last_pcol_td                =   None
        pols, freq_range            =   [], []
        freq = None

        tsys_found, gain_found      =   False, False
        _tsys_head                  =   {}
        allans, ind, pols           =   [],[], []
        ant_header_count            =   0
        ant_header                  =   False
        end_file                    =   False
        antenna_changed             =   False
        gain_header                 =   ""
        
        this_an_gain_processed      =   False
        mount                       =   ''
        gain_missing                =   []
        
        yday_start, yday_end        =   datetimerange_fromfits(self.fitsfile)
        yyyy                        =   yday_start.split(':')[0]
        tsys_lines = self.tsystxt.split('\n')
        tsys_lines.append('__END__')
        pols_global, freq_range_global = [], []
        dic_header_an               =   {}
        with open(outfile, "w") as oa: 
            for ti,t in enumerate(tsys_lines):
                
                # --------- Check working Station/Antenna
                if 'tsys information for' in t.lower():
                    an=t.lower().replace('tsys information for','').replace(' ','').replace('-','').replace('!','').upper()
                    antenna_changed = True
                    allans.append(an)
                    this_an_gain_processed = False
                    ant_header = False

                # ---------- Check rcp,lcp,freq availability -> choose the header with closest timestamp
                if ti+1 < len(tsys_lines) and any(pol in tsys_lines[ti+1].lower() for pol in ['rcp', 'lcp']):
                    headv = [v for v in t.split(' ') if v]
                    for hv in headv:
                        if all(v in hv for v in [':', '-', '/']):                                                           # HACK: looks for the timestamp pattern unique to header
                            hv = hv.split('/')
                            timv = [f"{yyyy}:{t_hv.replace('-', ':')}" for t_hv in hv if t_hv]                        
                            if last_pcol_td is None or antenna_changed:#or last_pcol_td <= 999: #(Time(yday_start)- Time(timv[0])).value:             # checking closest timestamp
                                antenna_changed = False
                                last_pcol_td = (Time(yday_start)- Time(timv[0])).value
                                # print(last_pcol_td, "was last time diff", "timestamp from header:", timv)
                                pols, freq_range = [], []
                            # else:
                            #     print(last_pcol_td, "REJECTED: was last time diff", "timestamp from header:", timv)
                if any(pol in t.lower() for pol in ['rcp', 'lcp']):
                    p = [pol for pol in ['rcp', 'lcp'] if pol in t.lower()]
                    if p:
                        pols.append(p[0])
                        line = [l for l in t.split(' ') if l]
                        if ti-1>0 and not any(pol in tsys_lines[ti-1].lower() for pol in ['rcp', 'lcp']):                   # checking first row with freq
                            
                            if 'K' in str(line[-3]):
                                bw         = float(line[-3].replace('K',''))/2000
                            else:
                                bw         = float(line[-3].replace('M',''))/2
                            
                            freq_range = [str(float(line[-2].replace('MHz',''))-bw)]                                                       # HACK: hardcoded -2 might not be always true, check header info
                        if ti+1<len(tsys_lines) and not any(pol in tsys_lines[ti+1].lower() for pol in ['rcp', 'lcp']):     # checking last row with freq in TSYS header
                            freq_range.append(str(float(line[-2].replace('MHz',''))+bw))                                                   # HACK: hardcoded "MHz" can be avoided
                        if freq_range and not this_an_gain_processed:
                            ## TODO: we should store R{nrcp},L{nlcp} in a dict 
                            # for freq in freq_range:
                                # band = check_band(freq/1e3) # as freq in MHz -> GHz
                                # ---> change indent for following:
                            freq = abs(float(freq_range[0]))
                            
                            mount, dpfu, poly           =   find_gain_fromgaintable(fitsfile=self.fitsfile, vlbagainfile=vlbagainfile, an=an, date=self.dateobs, freq=freq)
                            if mount is None:
                                mount, dpfu, poly       =   find_gain(vlbagainfile, an, self.dateobs, freq)
                            this_an_gain_processed = True
                            if not mount:
                                gain_missing.append(an)
                                # if band not in dic_header_an: dic_header_an[band] = {an:{}}
                                # dic_header_an[band][an] = {"mount":mount, "dpfu":dpfu, "poly":poly, 'pols': pols, 'freq' :freq}                            
                            
                # ---------- Gathering TSYS header info
                if 'TSYS ' in t:
                    tsys_found          =   True

                    tv                  =   [tt for tt in t.split(' ') if tt]
                    tv.remove('TSYS')
                    tv.remove('/')

                    d_val               =   {}
                    for i,each_tv in enumerate(tv): 
                        if '=' in each_tv:
                            tv_val      =   ''
                            try:
                                tv_val  =   float(tv[i+1])
                            except:
                                tv_val  =   0#str(tv[i+1])                      # HACK: if the value is not numeric consider 0. 
                                                                                        # Only verified with TIMEOFF=* -> AIPS TASK ANTAB -> TIMEOFF=0
                            d_val[str(tv[i-1])] =   tv_val
                            tv.pop(i-1)
                            tv.pop(i-1)
                            tv.pop(i-1)

                    _tsys_head[str(tv[0])]      =   d_val        
                    

                elif t and t[0]=='/':
                    tsys_found=False
                    
                # ---------- Create main_antab_txt
                elif tsys_found:                                                # HACK: Using elif (instead of if) avoids finding 'TSYS:'

                    if t and t[0]!='!':
                        if mount and an in _tsys_head:
                            if not ant_header:
                                if pols:
                                    rc,lc       =   0,0
                                    # print(f"pols={pols} {an} , {len(ind)}")
                                    for i,pol in enumerate(pols):

                                        if 'rcp' in pol:
                                            rc          +=  1
                                            ind.append(f"'R{rc}'")
                                        elif 'lcp' in pol:
                                            lc          +=  1
                                            ind.append(f"'L{lc}'")

                                an_values               =   [f"{k.upper()}={v}" for k,v in _tsys_head[an].items()]

                                antab_header            =   f"GAIN {an} {mount} DPFU={', '.join(map(str,dpfu))} "
                                # antab_header            +=  f"FREQ={', '.join(freq_range)} "
                                antab_header            +=  f"POLY={', '.join(map(str,poly))} /"
                                antab_header            +=  f"\nTSYS {an} {' '.join(an_values)} INDEX= {','.join(ind)} /\n"
                                pols, ind               =   [], []
                                # print(antab_header)
                                if ant_header_count:
                                    main_antab_txt          += '/\n'
                                    
                                main_antab_txt         +=  antab_header
                                ant_header_count       +=  1
                                ant_header              =   True
                            rowv = [v for v in t.split('!')[0].split(' ') if v]
                            if len(rowv)>1: 
                                if '.' in rowv[1]:
                                    hh,mm                   =   rowv[1].split(':')
                                    sec_dec                 =   mm.split('.')[1]
                                    mm                      =   f"{mm.split('.')[0]}:{float(sec_dec) * 0.6*0.1**len(sec_dec)}"
                                    rowv[1]                 =   f"{hh}:{mm}"

                                hh_strp, mm_strp, ss_strp = rowv[1].split(':')
                                
                                fixed_time = (datetime.strptime("0:0:0.0", "%H:%M:%S.%f") + timedelta(hours=float(hh_strp), minutes=float(mm_strp),seconds=float(ss_strp))).strftime("%H:%M:%S.%f")
                                yday_row                    =   Time(f"{yyyy}:{rowv[0]}:{fixed_time}")
                                row_validation              =   True#yday_start < yday_row < yday_end
                                #idx_freq                   =   [idxf for idxf in range(ind) freq_start < freq_ro]
                                if row_validation:

                                    row_vv                  =   [v for v in t.split('!')[0].split(' ') if v]
                                    row_vv[1]               =   yday_row.strftime(f'%H:%M:%S.%f')[:-2]
                                    row_vv                  =   " ".join(row_vv)
                                    # print(row_vv)
                                    main_antab_txt          +=  f"{row_vv}\n"


                        if main_antab_txt:
                            # print(main_antab_txt)
                            oa.write(main_antab_txt)
                            main_antab_txt=''
                if '__END__' in t:  
                    end_file = True
                    if end_file:
                            oa.write('/')
                            
        return allans, _tsys_head, gain_missing
    


def parse_equals(gain_dic, antb_line_cols):
    key                             =   "undefined"
    for val in antb_line_cols:
        val                         =   val.replace("'", "")
        val                         =   val.replace('"', "")
        
        if "=" in val:
            key, firstvalue         =   val.split("=")
            gain_dic[key]  =    []
            if firstvalue.strip():
                gain_dic[key]  =   [firstvalue.strip()]
        else:
            if not "," in val:
                gain_dic[key].append(val)
            else:
                gain_dic[key].extend(val.split(','))
    return gain_dic
                    
def parse_gain_from_antab(gain_dic, antb_line_cols):
    gain_dic           =   {}
    gain_dic['MOUNT']  =   antb_line_cols[2].strip()
    rest                        =   antb_line_cols[3:-1]
    gain_dic                    =   parse_equals(gain_dic, rest)
    return gain_dic

def parse_tsys_from_antab(tsys_dic, antb_line_cols):
    rest               =    antb_line_cols[2:-1]
    tsys_dic           =   parse_equals(tsys_dic, rest)
    tsys_dic['data']   =   []
    return tsys_dic
    

def parse_antab(antabfile, fitsfile):
    with open(antabfile) as antb:
        gain_dic                =   {}
        tsys_dic                =   {}
        tsys_row                =   False
        tsys_head_recorded      =   False
        mintime, maxtime        =   "", ""
        for antb_line in antb.readlines():
            antb_line_cols      =   antb_line.split(" ")
            firstcol            =   antb_line_cols[0].strip()
            
            if firstcol in ["GAIN", "TSYS"]:
                antenna         =   antb_line_cols[1].strip()
                if firstcol == "GAIN":                                          # Record gain header
                    tsys_row    =   False   
                    gain_dic[antenna]    =   {}
                    gain_dic[antenna]    =   parse_gain_from_antab(gain_dic[antenna], antb_line_cols)
                    
                elif firstcol == "TSYS":                                        # Record tsys header
                    tsys_row            =   True
                    tsys_head_recorded  =   True
                    if not antenna in tsys_dic:  tsys_dic[antenna]   =   {}
                    tsys_dic[antenna]   =   parse_tsys_from_antab(tsys_dic[antenna], antb_line_cols)
                    
            if tsys_row:
                if tsys_head_recorded:
                    tsys_head_recorded  =   False
                else:
                    if firstcol != "/":                                         # Record tsys Data
                        antb_line_cols[-1]  =   antb_line_cols[-1].replace("\n", "")
                        # tsys_dic[antenna]['data'].append(antb_line_cols)
                        
                        s               =   " ".join(antb_line_cols[:2])
                        tsys_values     =   [float(v) for v in antb_line_cols[2:]]
                        yy              =   get_dateobs(fitsfile=fitsfile).year
                        # dt              =   datetime.strptime(s, "%j %H:%M:%S.%f").replace(year=yy) # does not consider leap year
                        dt              =   datetime.strptime(f"{yy} {s}", "%Y %j %H:%M:%S.%f")
                        if not mintime or mintime> dt: mintime = dt
                        if not maxtime or maxtime< dt: maxtime = dt
                            
                        tsys_dic[antenna]['data'].append([str(dt), tsys_values])
                        tsys_dic["start_time"] = mintime
                        tsys_dic["end_time"] = maxtime
    return {"gain_dic": gain_dic, "tsys_dic": tsys_dic}


def find_gain_fromgaintable(fitsfile, vlbagainfile, an, freq, gaintbname="GAIN_CURVE", date="", verbose=True):
    """
    assumes DATE-OBS wont change anything.
    
    """
    from astropy.io import fits
    hdul    = fits.open(fitsfile, mode="readonly")
    mount, sensitivity, poly = None, None, None
    
    if gaintbname in hdul:
        
        tb_ant  = hdul['ANTENNA'].data

        idx_tba =   list(tb_ant['ANNAME']).index(an)
        anid    =   tb_ant['ANTENNA_NO'][idx_tba]
        pola    =   tb_ant['POLTYA'][idx_tba]

        gaintb  =   hdul[gaintbname].data
        idx_tbg = gaintb['ANTENNA_NO']==anid

        reffreq = hdul['FREQUENCY'].header['REF_FREQ']
        freqtb  = hdul['FREQUENCY'].data
        ntab    = hdul[gaintbname].header['NO_TABS']
        dic_band = {}

        for i,freqid in enumerate(freqtb['FREQID']):
            bandfreq                    = reffreq + freqtb['BANDFREQ'][i]
            for j,freq_sel in enumerate(bandfreq):
                band                    = check_band(freq_sel/1e9)
                if not band in dic_band: 
                    dic_band[band]      =  {j:freq_sel}
                else:
                    dic_band[band][j]   = freq_sel

        freq_given_Hz           = freq*1e6           # because freq is in MHz
        given_band              = check_band(freq_given_Hz/1e9)
        
        idx_band_seq            = list(dic_band[given_band].keys())

        pol1g                   =   np.max(gaintb[idx_tbg]['SENS_1'][0][idx_band_seq])                                      # HACK : hardcoded index 0 of the array result
        pol2g                   =   np.max(gaintb[idx_tbg]['SENS_2'][0][idx_band_seq]) if 'SENS_2' in list(gaintb.dtype.fields.keys()) else pol1g

        sensitivity             = [pol1g, pol2g] if pola =='R' else [pol2g, pol1g]
        an_gain                 = parse_vlbagain(vlbagainfile,an, freq=freq)
        mount                   = an_gain['MOUNT'].values[-1] if not an_gain.empty else "ALTAZ"

        nchan                   = len(freqtb['BANDFREQ'][0])                                                                   # HACK: assumes freqid 0
        polytb                  = gaintb[idx_tbg]['GAIN_1'][0].reshape(nchan,ntab)[idx_band_seq][0]
        poly                    = []
        for polyv in polytb:
            if polyv==0:break
            poly.append(polyv)
        if mount is not None and verbose:
            print(f"\t{gaintbname} found! values registered for {an}")
    return mount, sensitivity, poly

def find_gain(vlbagainfile, an, obsdate, freq):
    """
    Reads the vlba_gain.keys file and returns the GAIN value associated to the ANTENNA.

    Input
    ---

    :vlbagainfile:      (str)
                        path of the vlbagainfile.

    :an:                (str)
                        antenna name

    :obsdate:           (datetime.datetime object)
                        datetime object to compare GAIN values from

    :freq:              (float)
                        frequency value in MHz

    Returns 
    ---
    (MOUNT, DPFU, POLY)
    The GAIN information associated with the ANTENNA from the vlba_gains.key file.
    
    e.g

    >>> find_gain('vlba.gains','SC', daterange=datetime(2015,5,1), freq=6000)
    [output]
    SC GAIN ALTAZ DPFU = 0.111, 0.104 POLY = 1.0 /
    """
    mount, dpfu, poly = None, None, None
    an_gain = parse_vlbagain(vlbagainfile,an, freq=freq)
    
    an_gain['date_comp'] = [obsdate]*len(an_gain)
    found_date = an_gain.loc[an_gain['date_comp'].between(an_gain['FROM'],an_gain['TO'])]
    idx_by_nearest_freq = abs(found_date['FREQ'] - freq).sort_values(ascending=True).index   
    try:
        df_selected = an_gain.iloc[idx_by_nearest_freq[0]]
        mount, dpfu, poly = df_selected['MOUNT'], df_selected['DPFU'], df_selected['POLY']
    except:
        print(f"failed for {an} with {obsdate} and {freq}MHz")
    # print(f"{an} GAIN {df_selected['MOUNT']} DPFU = {', '.join(map(str,df_selected['DPFU']))} POLY = {', '.join(map(str,df_selected['POLY']))} /")
    return mount, dpfu, poly


def get_vlbagains(fl='vlba_gains.key', outfile='vlba_gains.key'):
    from contextlib import closing
    txt = None
    # with closing(request.urlopen(f'ftp://anonymous:vasco_pythonpackage@ftp.aoc.nrao.edu/pub/{fl}')) as r:
    with closing(request.urlopen(f'http://www.vlba.nrao.edu/astro/VOBS/astronomy/{fl}')) as r:    
        txt = r.read()
        if outfile:
            with open(outfile, 'wb') as cvlba:
                cvlba.write(txt)
    return txt

def parseval(val):
    if ' ' in val:
        try:
            val = [int(v) for v in val.split(' ') if v]
        except:
            try:
                val = [float(v) for v in val.split(' ') if v]
            except:
                val = [str(v) for v in val.split(' ') if v]            
    else:
        try:
            val = int(val)
        except:
            try:
                val = float(val)
            except:
                val = str(val)
                       
    return val

def parse_block_head(block_head):
    psv= [parseval(num) for num in block_head.split(' ') if num]
    workr = psv.copy()
    for tx in workr:
        if isinstance(tx, str) and not ('(' in tx and ')' in tx):                
                psv.remove(tx)
    if psv:
        pol = [val for val in psv if isinstance(val, str)][0].replace('(','').replace(')','').split(',')
    meas = psv[:len(pol)]
    proj = psv[len(pol)+1:]

    return meas,proj

def parse_vlbagain_anblock(block):
    dc = {'ANNAME':'', 'MOUNT':'', 'DPFU':[], 'POLY':[],
          'measurements':(), # measurements can be already checked before the parsing of these texts
                'BAND':'', 'TIMERANG':[],'FREQ':0., 'COMMENT':'', 'TS':[], 'TR':[], 'TCAL':[], 'FT':[]
         }

    for tx in block.split('\n'):
        tx=" = ".join(tx.split('='))   

        tx = [t for t in tx.split(' ') if t]
    #     tx_len = len(tx)
        if tx:
            if '/' in tx:
                dc['ANNAME'] = tx[0]
                dc['MOUNT'] = tx[2]
            for ti,t in enumerate(tx):        
                if '=' in t:            
                    tx_val = []
                    if ti-1>=0 and tx[ti-1] in dc:
                        _key = tx[ti-1].lstrip().strip()                
                        if ti+1<=len(tx):
                            if not '=' in tx[ti+1]:
                                k,pool = tx[ti-1], tx[ti+1:]

                                for j, val in enumerate(pool):

                                    if j+1<=len(pool):
                                        if not j+1==len(pool) and pool[j+1]=='=':
                                            break
                                        parsed_val = parseval(str(val).replace(',',' ').strip())

                                        if parsed_val!='/':
                                            if _key=='POLY' and isinstance(parsed_val, list):
#                                                 print(parsed_val)
                                                parsed_val = [pv for pv in parsed_val if pv]
                                                tx_val.extend(parsed_val)
                                            else:
                                                tx_val.append(parsed_val)                        
                            else:   
                                tx_val = parseval(str(tx[ti+1].strip()))
                        dc[_key] = tx_val
    return dc

def parse_vlbagain(vlbagainfile, an='LA', freq=0., meas_upper=[10,10],):
    """
    Converts vlba_gains.key file to pandas dataframe
    """
    from pandas import DataFrame as df
    countan = 0
    headstart = False
    meas,proj = [11,11], [1,1]
    idx=0
    dfable = []
    with open(vlbagainfile, 'r') as vg:
        vglines = vg.readlines()
        tx=''
        for gi,vgl in enumerate(vglines):
            if all(headk in vgl.lower() for headk in ['the', 'following', 'are', 'based']): 
                meas,proj = parse_block_head(vgl)
                headstart=True
                
            if vgl[0]!='!':
                if vgl=='\n':
                    headstart=True
                    tx=''
                if len(vgl)>3 and headstart:
                    tx+=vgl                    
                if '/\n' in vgl:
                    if an in vgl[:4]:
                        countan+=1
                        dc = parse_vlbagain_anblock(tx)
                        # print(dc,meas)
                        if meas>meas_upper:
                            freq_validation = check_band(dc['FREQ'][0]/1000)==check_band(freq/1000)
                            if dc['ANNAME']==an and freq_validation:
                                dfable.append([dc['MOUNT'],dc['DPFU'], dc['POLY'], datetime(*dc['TIMERANG'][0]),datetime(*dc['TIMERANG'][1]),dc['FREQ'][0]])
                    tx=''
                    headstart=False
    return df(data=dfable, columns=['MOUNT','DPFU', 'POLY', 'FROM', 'TO', 'FREQ'])



def get_tsys_txt_fromtsmcallog(cal_vlbafile):
    """
    Returns
    ---
    
    Tsys text: contains the whole tsys block extracted from the TSM log file
    Timerange From: 'yyyyMONdd'
    Timerange To: 'yyyyMONdd'
    """
    tsysv,fr,to = '', None, None
    with open(cal_vlbafile, 'r') as cvlba:
        tsys_text = False
        tsm_lines = cvlba.readlines()
        for li,line in enumerate(tsm_lines):            
            if all(reqtxt in line.lower() for reqtxt in ['tsys', 'information']):
                tsys_text=True
            if li-1>0 and tsys_text and all(k in tsm_lines[li-1].lower() for k in ['for', 'timerange']):
                timerange_text = tsm_lines[li-1].split('to')
                to = timerange_text[1].split('at')[0].strip().split('/')[0]
                fr = [txt for txt in timerange_text[0].split('at')[0].split(' ') if txt]
                fr = fr[-1].strip().split('/')[0]
            if '/' in line[0]:
                tsys_text=False
            if tsys_text: tsysv += line
    return tsysv, fr, to