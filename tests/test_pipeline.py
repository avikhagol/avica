from vasco.pipe.main import VascoPipeline
from pathlib import Path

def test_config():
    from vasco.pipe.main import VascoPipeline
    from vasco.pipe.core import PipelineContext, NamedTuple

    pipe = VascoPipeline(pipe_params={"fitsfiles": ["/"+"home/avi/intelligence/jupyter/vscode/BW034/wd_2/raw/VLBA_VSN001540_file10.uvfits"]})

    
    print(pipe.check_config_requirements("preprocess_fitsidi"))

def test_pipearch():
    
    from vasco.pipe.core import PipelineStepBase, VascoPipelineCore, PipelineStepValidatorBase, B,BC, X, Y, D
    from vasco.pipe.config import PipeConfig
    
    class DemoValidator(PipelineStepValidatorBase):
        name="demovalidator"
        run_after=False
        def run(self, demo_name,aloo, lelo, tamatar, **kwargs):
            print(f"validating {demo_name}")
            return super().run(**kwargs)
        
    class DemoStep(PipelineStepBase):
        name = "demo_step"
        validate_by = [DemoValidator]
        def run(self, kabbadi, wala, aaya):
            return self.result
        
    class DemoPipeline(VascoPipelineCore):
        def __init__(self, pipe_params):
            steps_to_run = [DemoStep]
            super().__init__(pipe_params=pipe_params, steps=steps_to_run)

        def execute(self):
            return super().execute()
    pipe = DemoPipeline(pipe_params={"fitsfiles": ["/"+"home/avi/intelligence/jupyter/vscode/BW034/wd_2/raw/VLBA_VSN001540_file10.uvfits"]})
    
    print()
    for name, status in pipe.check_config_requirements(step="demo_step").items():
        if not any([status.has_default, status.in_input_config, status.in_context]):
            print(f"  {B}! {D}{name:<15}·{X} {Y}missing{X}")
            
    pipe.execute()
    
    

def test_preprocess_fitsidi():
    """
    _______________________________________________
    
    Executes each pipeline steps:
     - check all imports
     - preprocess FITS-IDI
        - check input parameter requirements
        - check validations
        - run step
        - check results    
    """
    # # testfits =   "test_VLBA_VSN001540_file10.uvfits"
    # fitsfile = "data/VLBA_VSN001024_file33.uvfits"
    # testfits =   "vlba_VSN001024_file33.uvfits"
    # fitsfile = "/mnt/6438D98627D1388F/Intelligence/jupyter/BW034/wd_1/raw/VLBA_VSN001540_file10.uvfits"
    
    # from vasco.fitsidiutil import ObservationSummary, SplitData, fitsidi_check, read_idi
    # from vasco.fitsidiutil.io import FITS_TYPE_MAP
    
    # s = SplitData(
    #     inpfits =   fitsfile,
    #     outfits =   testfits,
    #     verbose=True
        
    # )
    # s.split(
    #     source_ids=[1,20,23,24]
    # )
    
    
    # hdu1 = read_idi(testfits)
    # hdu2 = read_idi(fitsfile)

    # print(ObservationSummary(fitsfilepaths=testfits).to_polars())
    
    
    # ________________________________________
    
    
    # pipe_params={
    #             "folder_for_fits": ".",
    #              "target_dir" : "reduction/", 
    #             # "folder_for_fits": "/mnt/6438D98627D1388F/Intelligence/jupyter/BW034/wd_1/raw/",
    #              "primary_value": "1124+571", 
    #             #  "picard_dir":"/mnt/6438D98627D1388F/Intelligence/env/rPicard/picard",
    #              "casadir":"/home/avi/intelligence/env/casa-6.7.0-31-py3.10.el8/",
    #              "rfc_catalogfile":"rfc_2024a_cat.txt",
    #             #  "csv_file":"/home/avi/intelligence/jupyter/vscode/100test.csv",
    #              "fitsfilenames": [Path(testfits).name],
    #              }
    
    # main_pipeline = VascoPipeline(pipe_params=pipe_params)

    # # main_pipeline.filter_steps("preprocess_fitsidi","fits_to_ms")
    # # main_pipeline.filter_steps("vasco_fill_input","vasco_split_ms","rpicard")
    # result = main_pipeline.execute()
    # print(result)
    
    # _____________________________
    

    # hdu = read_idi(testfits)
    # print("\n--- dtype audit for UV_DATA ---")
    # for card in hdu['UV_DATA'].header.data:
    #     key   = card['key']
    #     dtype = card['dtype']
    #     value = card['value']
    #     code  = FITS_TYPE_MAP.get(dtype, {}).get('code', '?')
        
    #     # flag anything that looks numeric but is typed as string
    #     is_suspicious = (code == 'C') and (key.startswith(('CDELT','CRPIX','CRVAL','MAXIS','NMATRIX','EXTVER','TABREV','NO_','STK_','REF_','CHAN_','VIS_','TMATX')))
    #     if is_suspicious:
    #         print(f"  BAD  {key:12} dtype={code}  value={value!r}")
    
    
    # for hdu_name in hdu2.names:
    #     for hkey in hdu2[hdu_name].header.keys():
    #         h1_dtype = hdu1[hdu_name].header.get_dtype(hkey)
    #         h2_dtype = hdu2[hdu_name].header.get_dtype(hkey)

    #         assert FITS_TYPE_MAP[h1_dtype]['code'] == FITS_TYPE_MAP[h2_dtype]['code'], \
    #             f"{hdu_name}/{hkey}: dtype mismatch {FITS_TYPE_MAP[h1_dtype]['code']} vs {FITS_TYPE_MAP[h2_dtype]['code']}"

    #         assert hdu2[hdu_name].header[hkey] == hdu1[hdu_name].header[hkey], \
    #             f"{hdu_name}/{hkey}: value mismatch {hdu2[hdu_name].header[hkey]!r} vs {hdu1[hdu_name].header[hkey]!r}"
    