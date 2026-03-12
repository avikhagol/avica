from vasco.fitsidiutil import split as split_fits, listobs as listobs_fits, rm_hdr
from vasco.fitsidiutil.split import SPLIT
import sys
import typer
from typing import List
from astropy.time import Time, TimeDelta
# from astropy.io import fits
from fitsio import FITS
import numpy as np
from importlib.metadata import version
import json
from pathlib import Path
from vasco import rfc_find


fitsidiutil_cli = typer.Typer()


def version_callback(value: bool):
    if value:
        try:
            package_version = version(__package__ or __name__)
            typer.echo(f"{package_version}")
        except Exception as e:
            typer.echo(f"Error retrieving version: {e}")
        raise typer.Exit()


@fitsidiutil_cli.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version", "-v",
        help="Show the version and exit.",
        callback=version_callback,
        is_eager=True,  
        )
    ):
    ...

@fitsidiutil_cli.command()
def split(
                        fitsfilepath,
                        outfitsfilepath,
                        sids = None,
                        baseline_ids = None,
                        freqids = None,
                        source_col  = "SOURCE",
                        baseline_col  = "BASELINE",
                        frequency_col  = "FREQID",
                        expr = "",
                        reindex : bool = False,
                        verbose : bool = False,
                        rml : List[str] = typer.Option([], help="List of table names to remove"),
                                                        ):
    from fitsidiutil.lib import dict_baseline
    
    sids = sids.split(',') if sids else None
    sids = [int(s) for s in sids] if sids else None
    
    freqids = freqids.split(',') if freqids else None
    freqids = [int(s) for s in freqids] if freqids else None
    
    if baseline_ids and 'auto' in baseline_ids: 
        baseline_ids        =   [str(basl) for basl in list(dict_baseline(fitsfile=fitsfilepath).keys())]
        baseline_ids        =   ",".join(baseline_ids)
        
    baseline_ids = baseline_ids.split(',') if baseline_ids else None
    baseline_ids = [int(bl) for bl in baseline_ids] if baseline_ids else None
    split_fits(fitsfilepath=fitsfilepath, outfitsfilepath=outfitsfilepath, sids=sids, baseline_ids=baseline_ids, freqids=freqids,
                      source_col=source_col, baseline_col=baseline_col, frequency_col=frequency_col, expression=expr, verbose=verbose)
    
    s = SPLIT(fitsfilepath, outfits=outfitsfilepath)
    s.update_header()
    if rml: 
        s.rm_tbl(rml)
    s.reindex(sel_freqids=freqids)


@fitsidiutil_cli.command()
def listobs(
    fitsfilepath:str,
    sids : str = None,
    scanlist_json : bool = True,
    scangap : int = 15,
    outdir : str = str(Path().cwd().absolute()), json_outfile : str = 'listobs.json',
    print_outfile : str = 'listobs_fits.out',
    scale_dateobs = 'utc', scale_data = 'tai',
    ):
    """
    print time_start, time_end, source_id, nrow, [tint]*nspw
    """
    sids = sids.split(',') if sids else None
    
    from obs import ListObs
    
    lobs = ListObs(fitsfilepath=fitsfilepath, sids=sids, time_scale_data=scale_data, scale_dateobs=scale_dateobs, scangap=scangap)
    # datalistobs =
    
    print_out   =   lobs.df_listobs.to_string()
    
    with open(f"{outdir}/{print_outfile}", 'w') as ppout:
        ppout.write(f"{print_out}")
    
    if scanlist_json: 
        with open(f"{outdir}/{json_outfile}", 'w') as lobs:
            jsonstr = json.dumps({'scanlist': lobs.scanlist, 'listobs':lobs.dict_listobs, 'sources': dic_sources})
            lobs.write(jsonstr)
    print(print_out)

@fitsidiutil_cli.command()
def rmhdu(fitsfilepath : str,
           hdu_index: int):
    rm_hdr(fitsfilepath=fitsfilepath, hdu_index=hdu_index-1)
    
@fitsidiutil_cli.command()
def split_x(
                        fitsfilepath : str,
                        outfitsfilepath : str,
                        classfilepath : str,
                        rfcfilepath : str = rfc_find(write=False),
                        wd : str = str(Path().cwd().absolute()),
                        listobsfile : str = typer.Option('', help="listobs json file to read the scanlist array, if not provied, will try to run the listobs on fitsfile."),
                        targets : str = typer.Option([], help="comma separated target sources, because by default only top 20 bright sources are included in the final table."),
                        baseline_ids = None,
                        freqids = None,
                        source_col  = "SOURCE",
                        baseline_col  = "BASELINE",
                        frequency_col  = "FREQID",
                        nfiltersource : str = typer.Option("20", help="filter sources if above this limit"), 
                        expr = "",
                        reindex : bool = False,
                        verbose : bool = False,
                        rml : List[str] = typer.Option([], help="List of table names to remove"),
                                                        ):
    from vasco.fitsio import df_search_brightcalib_rfc
    scanlist_arr = []
    targets = targets.split(',')
    nsources = None
    
    if not listobsfile:
        json_outfile = 'listobs.json'
        listobs(fitsfilepath,outdir = str(wd), json_outfile = json_outfile, print_outfile = 'listobs_fits.out', scale_dateobs = 'utc', scale_data = 'tai')
        listobsfile = f"{wd}/{json_outfile}"
        
    classoutfile = f"{wd}/class_search.out"
        
    with open(listobsfile, 'r') as sr:
        scanlist_arr = json.loads(sr.read())['scanlist']
    ffbuff = FITS(fitsfilepath, 'r')
    
    for hdu in ffbuff:
        if hdu.get_extname() == 'SOURCE':
            nsources = hdu.get_nrows()
    nfiltersource = int(nfiltersource)
    if int(nsources)>nfiltersource:
        sids = df_search_brightcalib_rfc(fitsfilepath, rfcfilepath, classfilepath, scanlist_arr, targets, outfile=classoutfile, nfilter_sources=nfiltersource)['sid'].values
        sids = [str(sid) for sid in sids]
        sids = ",".join(sids)
    else:
        sids = ''
        
    split(fitsfilepath, outfitsfilepath, sids, baseline_ids, freqids, source_col , baseline_col , frequency_col , expr, reindex, verbose, rml)

if __name__ == "__main__":
    fitsidiutil_cli()