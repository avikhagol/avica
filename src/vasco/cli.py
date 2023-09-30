from collections import defaultdict
from pathlib import Path
import argparse
from vasco.fits import _listobs, Targets as t

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

parser.add_argument('input_file', help='Give the input file path.', nargs='+')

plotting=parser.add_argument_group('plotting', """
                                   use plotms based arguments to generate plots in the terminal.""")
plotting.add_argument('-plist', '--parameter-list', help="list of parameters comma separated to fill in plotms")

op=parser.add_argument_group('operations',"""
                             use operations based on file type e.g., .FITS .MS
""")
op.add_argument('-l','--list-observation',help="lists all the useful details similar to listobs in CASA or listr in AIPS.", required=False, action="store", const="SCAN", nargs='?')
op.add_argument('-it','--identify-targets',help="find targets for phasecal, science and bright cal for FF", required=False, action="store_true")


args=parser.parse_args()


def params_fromlist(pl_value):
    params={}
    pl=pl_value.split(',')
    for i in range(len(pl)):
        if '=' in pl[i]:
            k,v=pl[i].split('=')
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

def _vitals_check(args):
    """
    checks input arguments and throws errors if something went wrong
    """
    status_check,desc, desc_arr=True,None,[]
    input_file=args.input_file
    if input_file:
        for file in input_file:
            if not Path(file).exists(): 
                status_check=False
                desc=f"Input file not found: '{file}'"
    return status_check, desc, desc_arr

def cli():
    input_file=args.input_file                                      # is a list
    status_check,desc, desc_arr=_vitals_check(args)

    if not status_check: 
        raise RuntimeError(desc)
    else:
        if args.parameter_list: 
            from vasco.helpers import vascolog, genplotms
            params=params_fromlist(args.parameter_list)
            print(f"created {genplotms(input_file,kind='png', **params)}")
        if args.list_observation:
            cardname=args.list_observation.split(',')
            for fitsfile in input_file: 
                print(Path(fitsfile).name)
                _listobs(fitsfile,cardname)
        if args.identify_targets:
            
            targets,sourcesl={},[]
            for fitsfile in input_file:
                print(Path(fitsfile).name)
                Targ=t(fitsfile)
                targ=Targ.identify_target
                for k,v in targ.items(): 
                    sourcesl.extend(v)
                    if k not in list(targets.keys()): targets[k]=v
                    elif v and (set(v) & set(sourcesl)): 
                        targets[k].extend(v)
                        targets[k]=list(set(targets[k]))

            print(targets)

if __name__=='__main__':
    cli()