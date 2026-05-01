from casatools import msmetadata, logsink
from avica.util import check_band
import numpy as np

avicalog=logsink('avica.casa_log')
avicalog.setlogfile='avica.casa_log'
avicalog.setglobal(True)

# -------                       Classes

class BandInfoMS:
    """
    ______________________________________________________

    Retrieve band information from a Measurement Set.

    Returns a dictionary of band metadata including band name, spectral windows,
    and reference frequencies, structured as follows:

    .. code-block:: python
        BandInfoMS(vis, min_expt=1.5).check_bands_ms
        {
            "<band>": {
                "spws":     [spw_id, ...],
                "reffreqs": [freq_hz, ...],
                "nobs":     int,
                "obs=<OBSID>": {
                    "scans": {
                        spw_id: [scan_id, ...]
                    }
                }
            }
        }

    Returns:
        dict: Band information keyed by band name.


    _____________________________________________________

    """
    def __init__(self, vis, min_expt, verbose=True, min_ant_scans=None):

        self.vis                =   vis
        self.verbose            =   verbose
        self.min_expt           =   min_expt

        self.msmd               =   msmetadata()

        # optional
        self.min_ant_scans      =   min_ant_scans or 2

        #
        self.msmd.open(self.vis)
        self.bands_dict         =   self.check_bands_ms()
        self.removable_antennas =   {band:[] for band in self.bands_dict}

    def check_bands_ms(self):
        """
        Retrieve band information from a Measurement Set.

        Returns a dictionary of band metadata including band name, spectral windows,
        and reference frequencies, structured as follows:

        .. code-block:: python

            BandInfoMS(vis, min_expt=1.5).check_bands_ms
            {
                "<band>": {
                    "spws":     [spw_id, ...],
                    "reffreqs": [freq_hz, ...],
                    "nobs":     int,
                    "obs=<OBSID>": {
                        "scans": {
                            spw_id: [scan_id, ...]
                        }
                    }
                }
            }

        Returns:
            dict: Band information keyed by band name.


        """

        spws = set()                            # get spws
        spwsforfields = self.msmd.spwsforfields()
        for spws_inf in spwsforfields.values():
            spws.update(spws_inf)

        d               = {}
        nobs            = self.msmd.nobservations()

        for obsid in range(nobs):               # collect {"band":{"spws":[], "reffreqs":[], "nobs":int,
                                                #                   "obs=OBSID": {"scans": {spw_id: [scans]]}} } }
            dic_scansforspws = self.msmd.scansforspws(obsid=obsid)

            for spw in dic_scansforspws:

                reffreq = self.msmd.reffreq(int(spw))['m0']['value']
                band    = str(check_band(reffreq/1.0E+09))
                if band not in d.keys():
                    d[band] = {}

                if 'spws' not in d[band]:
                    d[band]['spws']         =   [int(spw)]
                    d[band]['reffreqs']     =   [reffreq]
                    d[band]['nobs']         =   nobs


                else:
                    d[band]['spws'].extend([int(spw)])
                    d[band]['reffreqs'].extend([reffreq])

                if f'obs={obsid}' not in d[band]:
                    d[band][f'obs={obsid}'] =   {'scans': {int(spw): [int(spw_value) for spw_value in list(dic_scansforspws[spw])]}}#[

                else:
                    if "scans" in d[band][f'obs={obsid}']:
                        d[band][f'obs={obsid}']['scans'][int(spw)] = [int(spw_value) for spw_value in list(dic_scansforspws[spw])]
                    else:
                        raise ValueError(f"scans not found in {d[band].keys()}")

        return d

    def missing_antennas(self, band):
        from casatools import table
        spws = self.bands_dict[band]['spws']
        _tsys = f"{self.vis}/SYSCAL"
        _ants = f"{self.vis}/ANTENNA"

        tb_tsys, tb_ants = table(), table()

        tb_tsys.open(_tsys)
        tb_ants.open(_ants)


        tb_tsys.query(f"all(SPECTRAL_WINDOW_ID in {spws})")

        ants = tb_ants.getcol('NAME')
        tsys_ants = tb_tsys.getcol('ANTENNA_ID')

        tb_tsys.close(), tb_ants.close()

        tsys_missing_ants = list(set(range(len(ants))) - set(tsys_ants))
        self.removable_antennas[band] = ants[tsys_missing_ants]
        return self.removable_antennas[band]

    def get_band_detail(self, band):
        timeavg                         =   False
        dict_result                     =   {}
        # __________________________ missing_antennas


        for i,obsid in enumerate(range(self.bands_dict[band]['nobs'])):
            good_scans                  =   set()
            spws                            =   set([int(val) for val in self.bands_dict[band][f'obs={obsid}']['scans'].keys()])
            reffreqs                        =   [self.bands_dict[band]['reffreqs'][self.bands_dict[band]['spws'].index(spw)] for spw in spws]
            # reffreqs                        =   [self.bands_dict[self.bands_dict[band]['reffreqs'][refi] for refi in reffreqi]
            if not dict_result:
                dict_result                     =   {f"{band}{i}" : {"spws": spws, "reffreqs":reffreqs, "missing_antennas": list(self.missing_antennas(band))},}
            else:
                dict_result[f"{band}{i}"]       =   {"spws": spws, "reffreqs":reffreqs, "missing_antennas": list(self.missing_antennas(band))}

            for spw in spws:
                found_expt                  =   999

                #   ___________________ goodscans, min_expt

                for scan in self.bands_dict[band][f'obs={obsid}']['scans'][spw]:

                    expt                    =   self.msmd.exposuretime(scan=scan, spwid=spw, obsid=obsid)['value']
                    found_expt              =   expt if expt<found_expt else found_expt
                    ants_scan               =   [an for an in self.msmd.antennasforscan(scan) if self.msmd.antennanames(an)[0] not in self.removable_antennas[band]]
                    scan_times              =   self.msmd.timesforscan(scan)
                    if len(scan_times)>1 and len(ants_scan) >= self.min_ant_scans: good_scans.add(str(scan))                      # The scans with just one time sample are also bad

                if self.verbose: print(f"min exposure time for the spw {spw} (obs={obsid}) is {found_expt} | mean_freq={np.round(self.msmd.meanfreq(spw)/1e9,2)} GHz")

                # ______________________ nchan, chwidth
                chwidth_khz                 =   self.msmd.chanwidths(spw)/1e3
                nchan                       =   len(chwidth_khz)
                chwidth                     =   chwidth_khz.mean()

                if found_expt <= self.min_expt :   timeavg                     =   True

                bw_khz                          =   self.msmd.bandwidths(spw)/1e3
                dict_result[f"{band}{i}"][spw]          =   {"nchan":nchan, "chwidth":chwidth, "bw_khz":bw_khz, "good_scans":good_scans}


            dict_result[f"{band}{i}"]['timeavg']              =   timeavg

        return dict_result

    def spws(self, band):
        return self.bands_dict[band]['spws']
