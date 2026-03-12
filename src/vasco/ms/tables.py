from polars import DataFrame as pldf
import polars as pl
from casatools import table


def chk_tbl(subt1, subt2, relax_order=False):
    """
    subt1 and subt2 are subtables in polars dataframe
    Checks if subt2 has multiple copies of subt1.
    For each iteration i, compare row n from subt1 with row n * i from subt2
    """
    chk   = []
    dic_res = {}
    nrow1 = subt1.shape[0]
    nrow2 = subt2.shape[0]
    
    if relax_order and nrow1>nrow2:
        cmprow, subtcmp = nrow1, subt1
        nrow1, subt1 = nrow2, subt2
        nrow2, subt2 = cmprow, subtcmp
    
    niter = nrow2/nrow1
    
    if niter>1:
        if nrow2 % niter != 0:
            raise SystemExit(f"rownr {subt2.shape[0]} of subt2 is not the valid factor of the rownr {subt1.shape[0]} of subt1\nAborting!")
    else:
        for i in range(int(niter)):
            si = nrow1*i
            ei = si+nrow1
            chk.append((subt2[si:ei]==subt1).to_series().all())
    if all(chk):
        dic_res['dubplicate_row'] = [nrow1, nrow2]
    dic_res['duplicate'] = all(chk)
    dic_res['niter'] = niter
    

    return dic_res


def verifysubt_byeachelem(refvis, newvis):
    tb = table()
    tb.open(f"{refvis}")
    keywords =tb.keywordnames()
    tb.close()
    
    dic_kywchecked = {}
    if 'PHASE_CAL' in keywords:
        phcal_orig, phcal_shifted           = read_phasecal(refvis), read_phasecal(newvis)
        dic_kywchecked['PHASE_CAL']         = chk_tbl(phcal_orig, phcal_shifted)
    if 'WEATHER' in keywords:
        weather_orig, weather_shifted       = read_weather(refvis), read_weather(newvis)
        dic_kywchecked['WEATHER']           = chk_tbl(weather_orig, weather_shifted)
    if 'SYSCAL' in keywords:
        syscal_orig, syscal_shifted         = read_syscal(refvis), read_syscal(newvis)
        dic_kywchecked['SYSCAL']            = chk_tbl(syscal_orig, syscal_shifted)
    if 'ANTENNA' in keywords:
        ant_orig, ant_shifted               = read_antenna(refvis), read_antenna(newvis)
        dic_kywchecked['ANTENNA']           = chk_tbl(ant_orig, ant_shifted)
    if 'GAIN_CURVE' in keywords:
        gain_orig, gain_shifted             = read_gain(refvis), read_gain(newvis)
        dic_kywchecked['GAIN_CURVE']        = chk_tbl(gain_orig, gain_shifted)
    
    return dic_kywchecked

def verifysubt_nrows(refvis, newvis):
    tb = table()
    tb1 = table()
    defectedsubt = []
    tb.open(f"{refvis}")
    keywords_tochk =tb.keywordnames()
    tb.close()
    
    excludechk = ['MS_VERSION','DATA_DESCRIPTION','FEED','FLAG_CMD','FIELD','HISTORY']
    for keyw in excludechk:
        if keyw in keywords_tochk:
            keywords_tochk.remove(keyw)
    
    for subt in keywords_tochk:
        tb.open(f"{refvis}/{subt}")
        tb1.open(f"{newvis}/{subt}")
        
        nrows = tb.nrows()
        nrows1 = tb1.nrows()

        tb.close(), tb1.close()
        
        if nrows1!=nrows:
            defectedsubt.append(subt)
            if not nrows==0:
                print(subt,nrows,nrows1,nrows1/nrows)
            else:            
                print(subt,nrows,nrows1,'inf')
    return defectedsubt


def read_gain(vis, query=''):
    
    tb = table()
    tb.open(f"{vis}/GAIN_CURVE")
    if query:
        tb = tb.query(query)
    anid,feedid,spwid,time,interval,typ,numpoly,gain,sens = [tb.getcol(col) for col in ['ANTENNA_ID','FEED_ID','SPECTRAL_WINDOW_ID','TIME','INTERVAL','TYPE','NUM_POLY','GAIN','SENSITIVITY']]
    data = {
        'anid':anid,'feedid':feedid,'spwid':spwid,'time':time,'interval':interval,'typ':typ,'numpoly':numpoly,'gain':gain.T,'sens':sens.T,
    }
    tb.close()
    return pldf(data=data)

def read_antenna(vis, query=''):
    
    tb = table()
    tb.open(f"{vis}/ANTENNA")
    if query:
        tb = tb.query(query)
    offs, pos, typ, dishdiam, flag, mount, name, station = [tb.getcol(col) for col in ['OFFSET','POSITION', 'TYPE', 'DISH_DIAMETER', 'FLAG_ROW', 'MOUNT', 'NAME', 'STATION']]
    
    data = {
        'offs':offs.T, 'pos':pos.T, 'typ':typ, 'dishdiam':dishdiam, 'flag':flag, 'mount':mount, 'name':name, 'station':station,
    }
    tb.close()
    return pldf(data=data)

def read_weather(vis, query=''):
    
    tb = table()
    tb.open(f"{vis}/WEATHER")
    if query:
        tb = tb.query(query)
    anid, interval, time, dewpoint, h2o, ionose, pres, temp, winddir, windspeed = [tb.getcol(col) for col in ['ANTENNA_ID','INTERVAL','TIME','DEW_POINT','H2O','IONOS_ELECTRON','PRESSURE','TEMPERATURE','WIND_DIRECTION','WIND_SPEED']]
    tb.close()
    
    data = {
        'anid':anid, 'interval':interval, 'time':time, 'dewpoint':dewpoint, 'h2o':h2o, 'ionose':ionose, 'pres':pres, 'temp':temp, 'winddir':winddir, 'windspeed':windspeed
    }

    return pldf(data=data)
    
def read_syscal(vis, query=''):
    
    tb = table()
    tb.open(f"{vis}/SYSCAL")
    if query:
        tb = tb.query(query)
    
    anid,feedid,interval,spwid,time,tsys = [tb.getcol(col) for col in ['ANTENNA_ID', 'FEED_ID', 'INTERVAL', 'SPECTRAL_WINDOW_ID', 'TIME', 'TSYS']]
    tb.close()
    
    data = {
        'anid' : anid,
        'feedid' : feedid,
        'interval' : interval,
        'spwid' : spwid,
        'time' : time,
        'tsys1' : tsys[0],
    }

    if len(tsys)>1:
        data['tsys2'] = tsys[1]
        
    
    return pldf(data=data)


def read_phasecal(vis, query=''):
    tb = table()
    tb.open(f"{vis}/PHASE_CAL")
    if query:
        tb = tb.query(query)
    
    anid,feedid,spwid,time,interval,num_tones,tonefreq, phcal, cable_cal = [tb.getcol(col) for col in ['ANTENNA_ID','FEED_ID','SPECTRAL_WINDOW_ID','TIME', 'INTERVAL','NUM_TONES','TONE_FREQUENCY','PHASE_CAL','CABLE_CAL']]
    tb.close()
    
    data = {
        'anid' : anid,
        'feedid' : feedid,
        'interval' : interval,
        'spwid' : spwid,
        'time' : time,
        'num_tones': num_tones,
        'cable_cal': cable_cal,
        'phcalr':phcal.T.real,
        'phcali':phcal.T.imag,
        'tonefreqr':tonefreq.T.real,
        'tonefreqi':tonefreq.T.imag
        
    }            
    return pldf(data=data)


def fix_duplicatedrows(refvis, newvis, nomodify=True):
    tb = table()
    dic_subts    =  verifysubt_byeachelem(refvis, newvis)
    dupl_removed = 0
    tobe = "to be" if nomodify else " are"
    for subt, dic_subt in dic_subts.items():
        if dic_subt['duplicate'] and dic_subt['niter']>1:
            if not dupl_removed: print("...found duplicates")
            dupr = dic_subt['dubplicate_row']
            dupr = dupr[0]-1,dupr[1]-1
            dupr = list(range(*dupr))
            print("\t",subt, "rows", (dupr[0], dupr[-1]))
            dupl_removed+=1
            
            tb.open(f"{newvis}/{subt}", nomodify=nomodify)
            if not nomodify:
                tb.removerows(dupr)
                tb.flush()
            tb.close()
    
    ndupl = "No" if not dupl_removed else str(dupl_removed)
    print(f"{ndupl} duplicates {tobe} removed!")
