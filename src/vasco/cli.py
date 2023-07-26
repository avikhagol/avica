from collections import defaultdict
from pathlib import Path
import argparse
from vasco.fits import _listobs

parser = argparse.ArgumentParser('vasco', description="""
VLBI and SMILE source based CASA Optimizations (VASCO).""", 
formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument('-f','--input-file', help='Give the input file path.')

plotting=parser.add_argument_group('plotting', """
                                   use plotms based arguments to generate plots in the terminal.""")
plotting.add_argument('-plist', '--parameter-list', help="list of parameters comma separated to fill in plotms")

op=parser.add_argument_group('operations',"""
                             use operations based on file type e.g., .FITS .MS
""")
op.add_argument('-l','--list-observation',help="lists all the useful details similar to listobs in CASA.", required=False, action="store", const="SOURCE", nargs='?')


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

def cli():
    input_file=args.input_file
    if not Path(input_file).exists(): raise RuntimeError(f"Input file not found: '{input_file}'")
    if args.parameter_list: 
        from vasco.helpers import vascolog, genplotms
        params=params_fromlist(args.parameter_list)
        print(f"created {genplotms(input_file,kind='png', **params)}")
    if args.list_observation:
        cardname=args.list_observation.split(',')
        _listobs(input_file,cardname)

if __name__=='__main__':
    cli()