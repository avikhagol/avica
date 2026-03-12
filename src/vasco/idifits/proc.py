from fitsio import FITS
from astropy.time import Time
import numpy as np
from copy import deepcopy
import subprocess, shutil
from pathlib import Path

from vasco.idifits import ANTAB

def overlap_percentage(A_start, A_end, B_start, B_end):
    lenB = B_end - B_start
    overlap = max(0, min(A_end, B_end) - max(A_start, B_start))
    overlap_perc = np.round((overlap / lenB),4) * 100 if lenB > 0 else 0
    return overlap_perc

def tsys_exists(fitsfile):
    success                 =   False
    fo                      =   FITS(fitsfile, mode='r')

    starttime_tsys, starttime_uvd   =   None, None
    lasttime_tsys, lasttime_uvd     =   None, None
    print(fitsfile)
    i_uvd                           =   0
    for hdu in fo:
        if 'DATE-OBS' in hdu.read_header():
            refdate = hdu.read_header()['DATE-OBS']
            if '/' in refdate:
                refdate = refdate.split('/')
                if len(refdate[-1]) and int(refdate[-1])<100:
                    refdate[-1] = f"19{refdate[-1]}"
                    
                dd,mm,yyyy = refdate
                refdate = f"{yyyy}-{mm}-{dd}"
            zerotime=Time(refdate, format='isot',scale='utc')
        if hdu.get_extname() == 'UV_DATA':
            
            
            hdutime         =   hdu['TIME']
            refdate_uvd     =   hdu['DATE']
            nrow            =   hdu.get_nrows()
            szero           =   Time(refdate_uvd[0], format='jd', scale='tt')
            ezero           =   Time(refdate_uvd[nrow-1], format='jd', scale='tt')
            if i_uvd==0:
                starttime_uvd   =   Time(szero.mjd+hdutime[0], format='mjd', scale='tt')
            lasttime_uvd    =   Time(ezero.mjd+hdutime[nrow-1], format='mjd', scale='tt')
            
            i_uvd           +=  1
            
        if hdu.get_extname() == 'SYSTEM_TEMPERATURE':
            success         =   True
            hdutime         =   hdu.read_column('TIME')

            zerotime        =   Time(refdate, format='isot',scale='utc')
            scantime        =   Time(zerotime.mjd+hdutime, format='mjd', scale='tt')

            lasttime_tsys   =   max(scantime)
            starttime_tsys  =   min(scantime)
            
    if lasttime_tsys is None:
        success             =   False
        print("TSYS missing!")
    else:
        print(fitsfile)
        if overlap_percentage(starttime_tsys.mjd, lasttime_tsys.mjd, starttime_uvd.mjd, lasttime_uvd.mjd)>5:
                success     =   True
        else:
            print(f"<5% overlap b/w SYSTEM_TEMPERATURE and UV_DATA tables for {fitsfile}")
            success         =    False
                
    return success, starttime_tsys, lasttime_tsys, starttime_uvd, lasttime_uvd
    
def tsys_exists_in_fitsfiles(fitsfile, fitsfiles):
    success = False
    for ff in fitsfiles:
        if not fitsfile in ff:
            success, stff, ltff, stu, ltu = tsys_exists(ff)
            if not stff is None:
                print(fitsfile)
                ov_perc =overlap_percentage(stff.mjd, ltff.mjd, stu.mjd, ltu.mjd)
                
                if ov_perc>56.0:
                    success = True
                    break
                else:
                    missing_perc = np.round(100.0-ov_perc, 2)
                    print(f"Around {missing_perc}% of data is missing TSYS values!")
                
    return success
    
def count_freqids(fitsfile):
    count_freqids = 1
    fo = FITS(fitsfile)
    FREQID_CHK_COL = ['FREQUENCY', 'ANTENNA', 'GAIN_CURVE', 'SYSTEM_TEMPERATURE', 'SOURCE']
    multiple_freqid_present_in_chk_col = [all(hdu['FREQID'].read()==1) for col_forfreqid in FREQID_CHK_COL for hdu in fo if hdu.get_extname()==col_forfreqid]
    
    if not all(multiple_freqid_present_in_chk_col):
        # print(multiple_freqid_present_in_chk_col)
        count_freqids = len(fo['FREQUENCY']['FREQID'].read())   # TODO: should we count 2 if the FREQID in other table is only 1, while FREQUENCY has 1,2; gets flagged?
        
    return count_freqids

class PrepFITS:
    def __init__(self, fitsfiles, targets, metafolder, verbose, wd=None):
        
        self.fitsfiles                  =   fitsfiles
        self.tmpfs                      =   deepcopy(fitsfiles)
        self.targets                    =   targets
        self.metafolder                 =   metafolder
        self.verbose                    =   verbose
        self.wd                         =   wd
        
        self.success                    =   None
        self.desc                       =   ""
    
    def fix_header_exbyte(self):
        for ff_path in self.fitsfiles:
            cmd_fix = ['/data/avi/env/casapy38/bin/python3','/data/avi/bin/fits_check.py', ff_path, '--fix', '--minifix']
            subprocess.run(cmd_fix)
    
    def split_sources(self):
        """
        splits if file contains many sources
        """
        self.success, self.desc         =   False, "Failed"
        if len(self.fitsfiles)==1:
            if len(self.targets)-3 > 0:
                if len(self.targets)-3<10:      nfiltersource   =   25
                if len(self.targets)-5>10:
                    if len(self.targets)-5<10:  nfiltersource   =   30
                    if len(self.targets)-5<15:  nfiltersource   =   35
                    if len(self.targets)-5>=15: nfiltersource   =   60          # max
            else:
                nfiltersource           =   20
        else:
            nfiltersource               =   999
            if self.verbose: print("Since multiple fitsfile usually belongs to old projects, which means the filesize wont be a problem so we ignore them.")                                        # TODO: [FUTURE] scoop sources when there are many sources in multiple input filtsfile as well.        
        
        for i, ff_path in enumerate(self.fitsfiles):
            self.tmpfs[i]                       =   f"{Path(ff_path)}.tmp"
            cmd                                 =   ['/data/avi/env/py11/bin/fitsidiutil','split-x', ff_path, self.tmpfs[i], '/data/avi/d/smile/smile_complete_table.txt','--nfiltersource', str(nfiltersource),'--wd', str(self.metafolder),'--targets',",".join(self.targets),'--rfcfilepath','/data/avi/d/rfc_2024d/rfc_2024d_cat.txt']
            subprocess.run(cmd)
        if all(Path(tmpf).exists() for tmpf in self.tmpfs):        self.success, self.desc         =   True, "Splitted successfully!"
    
    def fix_hdutables(self):
        self.success, self.desc         =   False, "Failed"
        for i, tmpf in enumerate(self.tmpfs):
            fitsfile                    =   self.fitsfiles[i]
            cmd                         =   ['/data/avi/env/casapy38/bin/python3','/data/avi/bin/fits_check.py', tmpf, '--fix']
            subprocess.run(cmd)
            
            if Path(fitsfile).exists(): Path(fitsfile).unlink()
            shutil.move(str(Path(tmpf).absolute()), fitsfile)
    
    def split_freqid(self):
        for fitsfile in self.fitsfiles:
            freqids                     =   count_freqids(fitsfile)
            splitted_fitsfile           =   []
            if freqids>1:
                for i in range(freqids):
                    freqid              =   i+1
                    newfitsfile         =  str(Path(fitsfile).parent / f'{Path(fitsfile).stem}_freqid{freqid}') + Path(fitsfile).suffix
                    
                    # del_fl(wd_ifolder.parent / 'raw', 0, Path(newfitsfile).name, rm=True)
                    if Path(newfitsfile).exists(): Path(newfitsfile).unlink()
                    
                    if self.verbose     :   print(f"\nsplitting... FREQID=={freqid}")
                    cmd                 =   ['/data/avi/env/py11/bin/fitsidiutil','split', fitsfile, newfitsfile, '--freqids', str(freqid),'--verbose']
                    subprocess.run(cmd)
                    splitted_fitsfile.append(newfitsfile)                
        self.fitsfiles              =   self.fitsfiles + splitted_fitsfile
    
    def find_and_attach_antab(self, fitsfile, antabfile):
        ans_found                       =   set()
        dic_gf                          =   {}
        found_gf                        =   ''
        gain_missing                    =   []
        bsize                           =   float(FileSize('/dev/null').B)
        
        
        if self.verbose: print("finding tsys...")
        _, failed, rawfs            =   find_tsys(self.wd, fitsfile, 0, 0)                         
        if not rawfs:
            self.success, self.desc =   False, "Downloading failed!"
        else:
            for i,gf in enumerate(rawfs):
                if not '.tsys' in gf:
                    for gzippable_format in ['.Z', '.gz']:
                        if gzippable_format in gf:
                            subprocess.run(['gzip', '-d', gf])
                            gf          =   gf.replace(gzippable_format,'')
                    
                    try:
                        an              =   ANTAB(fitsfile, gf)
                        anfile          =   f'{antabfile}.{i}'
                        allans, _tsys_head, gain_missing    = an.gen_antab(anfile)
                        if bsize<float(FileSize(gf).B):
                            found_gf    =   gf
                            bsize       =   float(FileSize(gf).B)
                        if allans:  dic_gf[gf]=allans,gain_missing,anfile
                        ans_found.update(allans)
                    except Exception as e:
                        print(gf, e)
            for _file in dic_gf.keys():
                if found_gf!=_file:
                    del_fl(_file, rm=True)
            if found_gf: 
                Path(dic_gf[found_gf][2]).rename(Path(self.wd) / antabfile)
                tmpf            =   f"{Path(fitsfile)}.tmp"
                self.tmpfs[i]   =   tmpf
                if Path(tmpf).exists(): Path(tmpf).unlink()
                shutil.copy(str(Path(fitsfile).absolute()), tmpf)
                
                subprocess.run(['/data/avi/env/casapy38/bin/python3','/data/avi/gh/casa-vlbi/append_tsys.py', str(antabfile), tmpf])
                subprocess.run(['/data/avi/env/casapy38/bin/python3', '/data/avi/gh/casa-vlbi/append_gc.py', str(antabfile), tmpf])
                
                Path(fitsfile).unlink()
                Path(tmpf).rename(fitsfile)
    
    def attach_antab(self):
        antabfile                       =   Path(self.wd) / 'gc_dpfu_fromidi.ANTAB'
        self.success, self.desc         =   False, "Failed"
                
        for i, fitsfile in enumerate(self.fitsfiles):
            antabfile                   =   Path(self.wd) / f'gc_dpfu_fromidi.ANTAB.{i}'
            del_fl(Path(self.wd), fl=f'gc_dpfu_fromidi.ANTAB.{i}', rm=True)
            tsys_found, _, _ , _, _     = tsys_exists(fitsfile)
            if not tsys_found:
                if self.verbose: print("TSYS not found! Searching in other fitsfile")
                if not tsys_exists_in_fitsfiles(fitsfile, self.fitsfiles):
                    if self.verbose: print("TSYS not found in other fitsfiles")
                    self.find_and_attach_antab(fitsfile=fitsfile, antabfile=antabfile)
                    if self.verbose: print("Attaching TSYS finished!")
                else:
                    if self.verbose: print("TSYS exists in another fitsfile!")
        
    def validate(self):
        """
        tsys_exists_in_fitsfiles(fitsfile, self.fitsfiles)
        gc_exists_in_fitsfiles(fitsfile, self.fitsfiles)
        other things are already checked
        """
        
        self.success = all([tsys_exists(fitsfile)[0] and tsys_exists_in_fitsfiles(fitsfile, self.fitsfiles) for fitsfile in self.fitsfiles])
        
        if self.success:
            self.desc = "TSYS found"
        else:
            self.desc = "TSYS not found!"
        
        return self.success