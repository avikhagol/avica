#!/usr/bin/env python3
import argparse
from pathlib import Path

import json, time, shutil, subprocess
import resource
from avica.cli_new import avica_cli
import warnings

rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (26000, rlimit[1]))

avicadir = str(Path.home())+'/.avica/'

c={"x":"\033[0m","g":"\033[32m", "r":"\033[31m", "b":"\033[34m","c":"\033[36m","w":"\033[0m", "y":"\033[33m"}
rfc_filepath        =   f"{avicadir}/rfc_path.txt"

def ascii_art():
    art="""
   ____     __    __    _____     ____     ____
  (    )    ) )  ( (   (_   _)   / ___)   (    )
  / /\ \   ( (    ) )    | |    / /       / /\ \
 ( (__) )   \ \  / /     | |   ( (       ( (__) )
  )    (     \ \/ /      | |   ( (        )    (
 /  /\  \     \  /      _| |__  \ \___   /  /\  \
/__(  )__\     \/      /_____(   \____) /__(  )__\


    Automated VLBI pipeline in CASA.

    """
    return art

# parser = argparse.ArgumentParser('avica', description=ascii_art(),
# formatter_class=argparse.RawDescriptionHelpFormatter)

# parser.add_argument('input_file', help='Give the input file path.', nargs='*', default=rfc_filepath)
# parser.add_argument('--wd', help="current workdir; path used for the metafolder.", required=False, default=str(Path().cwd()))
# parser.add_argument('--mpi', help="use mpi when available", required=False, default=1)
# parser.add_argument('--ants', help="selected antennas, used for running operations using these antennas only", default='',required=False)
# parser.add_argument('--spws', help="selected spws, used for running operations using these spws only", default='',required=False)
# parser.add_argument('-S','--sources', help="selected fields i.e source names for operations.", required=False, default='')
# parser.add_argument('--from-meta', help='useful to run operations without determining metadata and tables again', action='store_true', required=False)
# parser.add_argument('--from-snr', help='to find sources from snr data second input in --input-file is the snr metafile; should have .avica in path; also needs --output-file else only prints output', action='store_true', required=False)
# parser.add_argument('-o','--output-file', help='Give the output file path.', required=False)
# parser.add_argument('--gen-antab', help='Generate ANTAB', action='store_true', required=False)
# parser.add_argument('--modify', help='Generate ANTAB', action='store_true', required=False)


# op=parser.add_argument_group('operations',"""
#                              use operations based on file type e.g., .FITS .MS
# """)
# op.add_argument('-l','--list-observation',help="lists all the useful details similar to listobs in CASA or listr in AIPS.", required=False, action="store", const="SCAN", nargs='?')
# op.add_argument('-t','--identify-targets',help="find targets for phasecal, science and bright cal for FF", required=False, action="store_true")
# op.add_argument('-r', '--find-refant', help="find refant by checking TSYS info", required=False, action="store_true")
# op.add_argument('--fix-dupltb', help="find duplicates in tables after the concat task and remove unnencessary rows", required=False, action="store_true")
# op.add_argument('-s', '--split-source', help='comma separated values of SOURCE_ID/SOURCE_NAME is used to select Sources to create a new FITS file/ MS.')
# op.add_argument('--to-B', help='Convert to B1920')

# cl=parser.add_argument_group('Calibrator List',"""
#                              use source based search on the calibrator list file.
# """)
# # cl.add_argument('--search', help='Comma separated list of sources', action="store_true")
# cl.add_argument('-C','--column', help='Comma separated values of column to get value for')

# def plot_ms(args):
#     from avica.diag import pl_scatter
#     from avica.ms import get_axs
#     from avica.ms.fringefit import get_tb_data
#     for msfile in args.input_file:
#         df_vis = get_axs(vis=msfile)
#     output  =   f"avica.diag/"
#     if args.sources:
#         fields  =   get_tb_data(f"{msfile}/FIELDS", ['NAME'])
#         fid     =   fields.compute().index(args.sources)
#         df_vis  =   df_vis[df_vis['field']==fid]
#         output  +=  f"{args.sources}_"
#     output  +=  f"{'_'.join(args.y)}_vs_{'_'.join(args.x)}"
#     pl_scatter(df_vis, x_labels=args.x, y_labels=args.y, color_axs=args.color_axs, cmap='jet', select=args.select, kind='png', output=output)
#     print(f"Plotting {args.input_file} with x={args.x} and y={args.y}")

# # pl = parser.add_subparsers(dest="command", required=True)

# # # plot_parser = pl.add_parser("plot", help="Plot data from a MS file")
# # # plot_parser.add_argument('input_file', nargs='*', help="Input MS file")
# # # plot_parser.add_argument("--x", type=str, required=True, help="X-axis parameter")
# # # plot_parser.add_argument("--y", type=str, required=True, help="Y-axis parameter")
# # # plot_parser.add_argument("--select", type=str, required=False, default='*', help="select data using query")
# # # plot_parser.add_argument("--color-axs", type=str, required=False, default='uvdist', help="choose column to plot the colour map")
# # # plot_parser.set_defaults(func=plot_ms)

# def params_fromlist(pl_value):
#     params={}
#     pl=pl_value.split(',')
#     for i,pl_i in enumerate(pl):
#         if '=' in pl_i:
#             k,v=pl_i.split('=')
#             if "'" in v: v=v.replace("'","")
#             else:
#                 try:
#                     v=int(v)
#                 except:
#                     try:
#                         v=float(v)
#                     except:
#                         v=str(v).strip()
#             params[k]=v
#     return params

# def casadir_find(write=True):
#     """
#     """
#     import readline, subprocess, shutil
#     readline.set_completer_delims('\t\n=')
#     readline.parse_and_bind("tab: complete")
#     cp_txt,do,auto  =   '', 'y', 'y'
#     casa_path       =   f"{avicadir}/casa_path.txt"
#     casadir         =   ''
#     if Path(casa_path).exists():
#         with open(casa_path, "r") as cp:
#             cp_txt  =   cp.readlines()[0]
#             if cp_txt:
#                 auto        =   'no'
#                 casadir     =   cp_txt
#                 print(f"There is a CASA path already written: {cp_txt}")
#     if write:
#         if cp_txt:
#             print(f"{c['c']} Are you sure you want to proceed overwriting?{c['x']}")
#             do          =   input("(y/n)")
#         if str(do).lower() in ["y", "yes"]:
#             print("Please enter your monolithic casa directory (eg /path/to/casa-CASA-xxx-xxx-py3.xxx/bin/):")

#             casadir=input()
#             with open(casa_path, 'w') as o:
#                 o.write(f"{casadir}/")
#         try:
#             subprocess.run([f"{casadir}/casa",'-v'],shell=False, stdout=subprocess.DEVNULL)
#         except FileNotFoundError:
#             print(f"{c['r']}Failed!{c['x']} The path '{casadir}' is not a valid casa directory")
#             print(f"Proceed with automatic search? (y/n):")
#             auto=input()
#     if str(auto).lower() in ["y", "yes"]:   casadir     =   Path(str(shutil.which("casa"))).resolve().parent

#     if Path(casadir).exists():              print(f"{c['g']}Success!{c['x']} Found this casa directory:{c['g']} {casadir}{c['x']}")
#     if not Path(casadir / 'mpicasa').exists():
#         print("Failed! mpicasa was not found")
#     else:
#         casadir = Path(casadir)
#         subprocess.run([f"{str(casadir)}/casa",'-v'],shell=False, stdout=subprocess.DEVNULL)
#         subprocess.run([f"{str(casadir)}/mpicasa",'-h'],shell=False, stdout=subprocess.DEVNULL)

#     print(f"casa_path : {casa_path}")
#     if not write:
#         return casadir

# def rfc_find(write=True):
#     """
#     check for file if exist for the rfc calibrator list.
#     returns path for the file.
#     """
#     import readline
#     readline.set_completer_delims('\t\n=')
#     readline.parse_and_bind("tab: complete")
#     rfc_txt,do      =   '','y'
#     filepath        =   rfc_filepath
#     if Path(filepath).exists():
#         with open(filepath, "r") as cp:
#             rfc_txt =   cp.readlines()[0]  if cp.readlines() else ""
#     if write:
#         if rfc_txt:
#             filepath    =   rfc_txt
#             print(f"There is a path already written: {rfc_txt}")
#             print(f"{c['c']} Are you sure you want to proceed overwriting?{c['x']}\n\n")
#             do          =   input("(y/n)")
#         if str(do).lower() in ["y", "yes"] and not rfc_txt:
#             print("Please enter the path for the ASCII file:")
#             rfc_txt     =   input()
#         with open(filepath, 'w') as o:
#             o.write(f"{rfc_txt}")
#     return rfc_txt

# def run_withmpi(args, cmd_args, n_core):
#     casadir     =   casadir_find(write=False)

#     # n_core      =   int(args.mpi)
#     thisdate    =   time.strftime('%F-%T', time.gmtime())
#     thisdate    =   thisdate.replace(':', '_')
#     errlogf     =   f'mpi_and_err.out_{thisdate}'
#     casalogf    =   f'casa.log_{thisdate}'
#     avicapath   =   shutil.which(__name__)
#     cmd         =   [f'{casadir}/mpicasa', '--oversubscribe', '-n', str(n_core), f'{casadir}/casa', '--agg', '--nogui', '--logfile', casalogf, '-c', avicapath]
#     if cmd_args:
#         cmd     =   cmd + cmd_args

#     if n_core==1:
#         print(" ".join(cmd))
#         exit(0)

#     elif cmd and avicapath:
#         rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
#         resource.setrlimit(resource.RLIMIT_NOFILE, (26000, rlimit[1]))
#         subprocess.run(cmd, stderr=open(errlogf,"+a"))
#         proc = subprocess.Popen(['tail', '-n', '5', errlogf], stdout=subprocess.PIPE)
#         lines = proc.stdout.read()
#         print(lines.decode('utf-8'))
#         if Path(casalogf).exists():
#             proc = subprocess.Popen(['tail', '-n', '5', casalogf], stdout=subprocess.PIPE)
#             lines = proc.stdout.read()
#             print(lines.decode('utf-8'))


# def _vitals_check(args, metafolder):
#     """
#     checks input arguments and throws errors if something went wrong
#     """
#     status_check,desc, desc_arr     =   True,'',[]
#     input_file                      =   args.input_file
#     if not Path(avicadir).exists():Path(avicadir).mkdir(parents=True,exist_ok=True)
#     if not Path(metafolder).exists():Path(metafolder).mkdir(parents=True,exist_ok=True)

#     if args.sources:
#         if args.identify_targets:
#             try:
#                 desc    =   open(rfc_filepath, 'r').read()
#             except FileNotFoundError:
#                 _       =   rfc_find(write=True)
#         elif args.find_refant:
#             desc        =   'refants'
#         elif args.split_source:
#             pass
#         else:
#             desc    =   'search source'
#     # if args.search:
#     #     if not args.sources:
#     #         status_check, desc = False, "Error: sources not specified"

#     elif input_file:
#         for file in input_file:
#             print(file)
#             if not Path(file).exists():
#                 status_check=False
#                 desc=f"Input file not found: '{file}'"

#     return status_check, desc, desc_arr

# def cli():
#     searchs                         =   False
#     args                            =   parser.parse_args()
#     input_file                      =   args.input_file                                      # is a list
#     output_file                     =   args.output_file

#     wd                              =   args.wd or Path(input_file[0]).parent
#     mpi                             =   int(args.mpi)
#     ants                            =   args.ants.split(',')
#     sources                         =   args.sources.split(',') if args.sources else []
#     spws                            =   args.spws if args.spws else []

#     metafolder                      =   str(f'{wd}/avica.meta')
#     status_check,desc, desc_arr     =   _vitals_check(args, metafolder)
#     new_tbls = new_meta             =   not args.from_meta
#     if args.gen_antab:
#         pout            =    """"""
#         from avica.idifits import ANTAB
#         fitsfile = input_file[0]
#         vlbacalf = input_file[1]
#         antabfile = f'{wd}/gc_dpfu_fromidi.ANTAB'
#         an = ANTAB(fitsfile, vlbacalf)
#         anfile = f'{antabfile}'
#         allans, _tsys_head, dmissing    = an.gen_antab(anfile)

#         pout+=f"missing         \t\t\t:{','.join(dmissing)}\n" if dmissing else "\n"
#         pout+=f"all antennas    \t:{','.join(allans)}\n" if allans else "\n"

#         print(pout)

#     if 'search source' in desc: searchs   =   True

#     if args.to_B:
#             from avica.helpers import J2000_toB1920
#             print(J2000_toB1920(args.to_B))
#     if not status_check:
#         raise RuntimeError(desc)
#     elif searchs:
#         # search_source = args.sources.split(',')
#         from avica.util import search_sources
#         source_found                =   search_sources(sources, str(rfc_find(write=False)))
#         if args.column:
#             source_found            =   source_found[args.column.split(',')]
#             print(f"search_sources({sources}, {desc})[{str(args.column.split(','))}]")
#         else:
#             print(f"search_sources({sources}, {desc})")
#         print(source_found)

#     else:
#         from avica.fits import _listobs, Targets as t, find_refant, split, fits
#         from avica.fitsio import listobs, IdentifySource as IdS, identify_sources_fromtarget
#         if args.fix_dupltb:
#             from avica.ms.tables import fix_duplicatedrows
#             nomodify = not args.modify
#             refvis = input_file[0]
#             newvis = input_file[1]

#             fix_duplicatedrows(refvis=refvis,newvis=newvis, nomodify=nomodify)
#         if args.list_observation:
#             cardname=args.list_observation.split(',')
#             for fitsfile in input_file:
#                 print(Path(fitsfile).name)
#                 # _listobs(fitsfile,cardname)
#                 print(listobs(fitsfile, asdf=True).to_string())
#         if args.identify_targets:
#             sources_dict        =   None
#             if args.from_snr and sources:
#                 from avica.ms import identify_sources_fromsnr_ms
#                 """
#                 works for
#                  either input_file = (msname, snr_avicametafile)
#                     or input_file = (msname)

#                 """
#                 msname          =   input_file[0]
#                 target          =   sources[0]
#                 sourcesf        =   input_file[1] if len(input_file)>1 and '.avica' in input_file[1] else None
#                 minsnr          =   7.0
#                 s               =   identify_sources_fromsnr_ms(msname, target_source=target,
#                                                                 caliblist_file=rfc_find(write=False),
#                                                                         snr_metafile=sourcesf, outfile=output_file,
#                                                                         flux_thres=minsnr, min_flux=minsnr, ncalib=6)
#                 print(s)
#             else:
#                 for fitsfile in input_file:
#                     if '.ms' not in str(fitsfile).lower():
#                         print(Path(fitsfile).name)
#                         if sources: print(sources)
#                         if not sources:
#                             ids = IdS(fitsfile)
#                             sources_dict = ids.identify_sources()
#                         else    :
#                             sources_dict = identify_sources_fromtarget(fitsfile=fitsfile, target_source=sources[0], rfcfile=rfc_find(write=False), verbose=True)
#                         print(sources_dict)
#                         if sources_dict :
#                             with open(f'{metafolder}/sources_fits.avica', 'w') as vrm: json.dump(sources_dict, vrm)
#                             sources = list(sources_dict.values())

#                     else:
#                         vis = fitsfile
#                         print(vis)
#                         from avica.ms import identify_sources_fromtarget_ms

#                         if sources:
#                                 s_dict = identify_sources_fromtarget_ms(vis, sources[0], rfc_find(write=False), metafolder=metafolder)
#                                 for band, sources_d in s_dict.items():
#                                     print(band, "band")
#                                     print(sources_d)
#                                     with open(f'{metafolder}/sources_ms_{band}.avica', 'w') as vrm: json.dump(sources_d, vrm)

#         if args.find_refant:
#             calibs = None
#             for fitsfile in input_file:
#                 if '.ms' not in str(fitsfile).lower():
#                     print(Path(fitsfile).name)
#                     refant_dict, print_outs  = find_refant(fitsfile, return_onmissing=True)

#                     if print_outs:
#                         with open(f'{metafolder}/refants_fits.avica', 'w') as vrm: json.dump(refant_dict.to_dict(), vrm)
#                         with open(f'{metafolder}/refants_fits.out', 'w') as vrm: vrm.write(print_outs)
#                     # print(refant_dict)
#                 else:
#                     from avica.ms import identify_refant_casa
#                     vis = fitsfile
#                     print(vis)
#                     refants, calibs, print_outs         =   identify_refant_casa(str(vis), new_tbls=new_tbls, new_meta=new_meta, mpi=mpi, target=sources[0],
#                                                                                  selected_sources=sources, refants=ants, spws=spws, verbose=True)
#                     refant_dict = {'refants': refants}
#                     with open(f'{metafolder}/sources.avica', 'w') as vrm: json.dump(calibs, vrm)
#                     with open(f'{metafolder}/refants.avica', 'w') as vrm: json.dump(refant_dict, vrm)
#                     with open(f'{metafolder}/refants_sources.out', 'w') as vrm: vrm.write(print_outs)
#                     print(refant_dict, calibs)
#         if sources and args.split_source:

#             for fl in input_file:
#                 print(fl)
#                 if '.ms' in fl.lower():
#                     if args.mpi and mpi>1:
#                         run_withmpi(args, ['-s', 'mpi', "-S", ",".join(sources), '--output-file', output_file, fl], mpi)
#                     elif mpi==1:
#                         parallel=False
#                         if args.split_source=='mpi': parallel=True
#                         from avica.ms import split_ms
#                         print("running without mpi") if not parallel else print("running with mpi")
#                         # run_withmpi(args, ['-s', ",".join(sources), '--output-file', output_file, fl])
#                         split_ms(vis=fl, outvis=output_file, source_list=sources, mpi=parallel)
#                 else:
#                     sids = args.sources.split(',')
#                     sids = [int(sid) for sid in sids]

#                     for fitsfile in fl:
#                         print(Path(fitsfile).name)
#                         hdul = fits.open(fitsfile)
#                         file_new = Path(hdul.filename())
#                         outfolder = ''
#                         file_new = f"{outfolder}{file_new.stem}_new{file_new.suffix}"
#                         new_fits = split(hdul, sids, file_new)

cli_new = avica_cli
if __name__=='__main__':
    cli_new()
