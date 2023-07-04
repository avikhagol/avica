from vasco.helpers import genplotms
import argparse
from collections import defaultdict
from pathlib import Path


parser = argparse.ArgumentParser('vasco',description="""
VLBI and SMILE source based CASA Optimizations (VASCO).""", formatter_class=argparse.RawDescriptionHelpFormatter)


plotting=parser.add_argument_group('plotting', """use plotms based arguments to generate plots in the terminal.""")

plotting.add_argument('-plist', '--parameter-list', help="list of parameters comma separated to fill in plotms")

args=parser.parse_args()


def cli():
    if args.parameter_list: print(args.parameter_list)
    

if __name__=='__main__':
    cli()