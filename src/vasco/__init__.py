import argparse
from pathlib import Path
import readline

vascodir = str(Path.home())+'/.vasco/'
c={"x":"\033[0m","g":"\033[32m", "r":"\033[31m", "b":"\033[34","c":"\033[36m","w":"\033[0m"}
rfc_filepath        =   f"{vascodir}/rfc_path.txt"

def ascii_art():
    art="""
____    ____  ___           _______.  ______   ______   
\   \  /   / /   \         /       | /      | /  __  \  
 \   \/   / /  ^  \       |   (----`|  ,----'|  |  |  | 
  \      / /  /_\  \       \   \    |  |     |  |  |  | 
   \    / /  _____  \  .----)   |   |  `----.|  `--'  | 
    \__/ /__/     \__\ |_______/     \______| \______/  

    VLBI and SMILE source based CASA Optimizations (VASCO).                                                        
    
    """
    return art

parser = argparse.ArgumentParser('vasco', description=ascii_art(), 
formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument('input_file', help='Give the input file path.', nargs='*', default=rfc_filepath)

op=parser.add_argument_group('operations',"""
                             use operations based on file type e.g., .FITS .MS
""")
op.add_argument('-l','--list-observation',help="lists all the useful details similar to listobs in CASA or listr in AIPS.", required=False, action="store", const="SCAN", nargs='?')
op.add_argument('-t','--identify-targets',help="find targets for phasecal, science and bright cal for FF", required=False, action="store_true")
op.add_argument('-r', '--find-refant', help="find refant by checking TSYS info", required=False, action="store_true")
op.add_argument('-s', '--split-source', help='comma separated values of SOURCE_ID is used to select Sources to create a new FITS file.')
op.add_argument('--to-B', help='Convert to B1920')

cl=parser.add_argument_group('Calibrator List',"""
                             use source based search on the calibrator list file.
""")
cl.add_argument('-S','--search-source', help='Comma separated list of sources to look for all the values')
cl.add_argument('-C','--column', help='Comma separated values of column to get value for')

def params_fromlist(pl_value):
    params={}
    pl=pl_value.split(',')
    for i,pl_i in enumerate(pl):
        if '=' in pl_i:
            k,v=pl_i.split('=')
            if "'" in v: v=v.replace("'","")
            else:
                try:
                    v=int(v)
                except:
                    try:
                        v=float(v)
                    except:
                        v=str(v).strip()
            params[k]=v
    return params
def rfc_find():
    """
    check for file if exist for the rfc calibrator list.
    returns path for the file.
    """

    readline.set_completer_delims('\t\n=')
    readline.parse_and_bind("tab: complete") 
    rfc_txt,do      =   '','y'
    filepath        =   rfc_filepath
    if Path(filepath).exists():
        with open(filepath, "r") as cp:
            rfc_txt =   cp.readlines()[0]
    if rfc_txt: 
        filepath    =   rfc_txt
        print(f"There is a path already written: {rfc_txt}")
        print(f"{c['c']} Are you sure you want to proceed overwriting?{c['x']}")
        do          =   input("(y/n)")
    if str(do).lower() in ["y", "yes"]:
        print("Please enter the path for the calibrator list ASCII file:")               
        rfc_txt     =   input()
        with open(filepath, 'w') as o:
            o.write(f"{rfc_txt}")
    return rfc_txt

def _vitals_check(args):
    """
    checks input arguments and throws errors if something went wrong
    """
    status_check,desc, desc_arr=True,None,[]
    input_file=args.input_file
    if not Path(vascodir).exists():Path(vascodir).mkdir(parents=True,exist_ok=True)
    if args.search_source:
        try:
            desc = open(rfc_filepath, 'r').read()
        except FileNotFoundError:
            rfc_file = rfc_find()
    elif input_file:
        for file in input_file:
            if not Path(file).exists(): 
                status_check=False
                desc=f"Input file not found: '{file}'"
    
    return status_check, desc, desc_arr



def cli():
    args=parser.parse_args()
    input_file=args.input_file                                      # is a list
    status_check,desc, desc_arr=_vitals_check(args)
    if args.to_B:
            from vasco.helpers import J2000_toB1920
            print(J2000_toB1920(args.to_B))

    elif args.search_source:
        sources = args.search_source.split(',')
        from vasco.util import search_source
        source_found = search_source(sources, str(desc))
        if args.column:
            source_found = source_found[args.column.split(',')]
        print(f"search_source({sources}, {desc})")
        print(source_found)
        
    elif not status_check: 
        raise RuntimeError(desc)
    else:
        from vasco.fits import _listobs, Targets as t, find_refant, identify_sources, split, fits
        if args.list_observation:
            cardname=args.list_observation.split(',')
            for fitsfile in input_file: 
                print(Path(fitsfile).name)
                _listobs(fitsfile,cardname)
        if args.identify_targets:
            
            # targets,sourcesl={},[]
            for fitsfile in input_file:
                print(Path(fitsfile).name)
                sources = identify_sources(fitsfile)
                # Targ=t(fitsfile)
                # targ=Targ.identify_target
                # for k,v in sources.items(): 
                #     sourcesl.extend(v)
                #     if k not in list(targets.keys()): targets[k]=v
                #     elif v and (set(v) & set(sourcesl)): 
                #         targets[k].extend(v)
                #         targets[k]=list(set(targets[k]))

                print(sources)
        if args.find_refant:
            for fitsfile in input_file:
                print(Path(fitsfile).name)
                refant_dict=find_refant(fitsfile)

        if args.split_source:
            sids = args.split_source.split(',')
            sids = [int(sid) for sid in sids]
            
            for fitsfile in input_file:
                print(Path(fitsfile).name)
                hdul = fits.open(fitsfile)
                file_new = Path(hdul.filename())
                outfolder = ''
                file_new = f"{outfolder}{file_new.stem}_new{file_new.suffix}"
                new_fits = split(hdul, sids, file_new)
        
if __name__=='__main__':
    cli()