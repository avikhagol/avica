#ifndef FITSIDI_LISTOBS
#define FITSIDI_LISTOBS
#include <iostream>
#include <vector>
#include <map>
#include <iomanip>
#include <cmath>
#include "fitsio.h"
#include <set>
#include <cstring>
#include <string>

static void print_fits_error(int status) {
    if (status) {
        fits_report_error(stderr, status);
        exit(status);
    }
}

struct RowData {
    double time_start;
    double time_end;
    int source;
    long nrows;
    std::vector<double> inttime; 
};

typedef struct RowData Struct;

class ListObs {
    public:
    
    static std::vector<RowData> listobs_fits(
        const std::string& fitsfilepath, 
        const std::optional<std::vector<long int>>& sids
    ) 
        {
        
        // initialize
        std::vector<long int> sids_vec = sids.value_or(std::vector<long int>{});
        const char* filename = fitsfilepath.c_str();
        int num_hdus;
        int status = 0;
        std::map<int, long> freqidToBandfreq; // Use long for nbandfreq

        bool filter_by_sids = !sids_vec.empty();                                                        //
        std::vector<RowData> results;
        std::set<long int> sids_set(sids_vec.begin(), sids_vec.end());

        fitsfile *in_fptr;                                                                             // read fitsfile
        fits_open_file(&in_fptr, filename, READONLY, &status);
        if (status) {
            std::cerr << "Error after open = " << status << std::endl;
                        fits_report_error(stderr, status);
                        fits_close_file(in_fptr, &status);
                        return results;
                    }

        fits_get_num_hdus(in_fptr, &num_hdus, &status);                                             // get number of hdus
        print_fits_error(status);
                                                                                                    // Variables to track the current SOURCE and its start/end times
        int current_source = -1;
        double current_time_start_mjd = 0.0, current_time_end_mjd = 0.0;
        long current_nrows = 0;
        int current_freqid = -1;
        double current_inttime = 0.0; // Declare current_inttime
        char timeColName[] = "TIME";
        char sourceColName[] = "SOURCE";
        char inttimColName[] = "INTTIM";
        char freqidColName[] = "FREQID";

        char frequencyHduName[] = "FREQUENCY";
        fits_movnam_hdu(in_fptr, BINARY_TBL, frequencyHduName, 0, &status);
        if (status) {
            std::cerr << "Error after status moving FREQ = " << status << std::endl;
            fits_report_error(stderr, status);
            fits_close_file(in_fptr, &status);
            return results;
        }
        int colnum_freqid;
        fits_get_colnum(in_fptr, CASEINSEN, freqidColName, &colnum_freqid, &status);                    
        if (status) {
            std::cerr << "Error after freqidColName  = " << status << std::endl;
            fits_report_error(stderr, status);
            fits_close_file(in_fptr, &status);
            return results;
        }
        int colnum_bandfreq;
        char bandfreqColName[] = "BANDFREQ";
        fits_get_colnum(in_fptr, CASEINSEN, bandfreqColName, &colnum_bandfreq, &status);
        if (status) {
            std::cerr << "Error after bandfreqColName = " << status << std::endl;
            fits_report_error(stderr, status);
            fits_close_file(in_fptr, &status);
            return results;
        }
    
        long nrows_freq;
        fits_get_num_rows(in_fptr, &nrows_freq, &status);
        if (status) {
            std::cerr << "Error after nrows_freq  = " << status << std::endl;
            fits_report_error(stderr, status);
            fits_close_file(in_fptr, &status);
            return results;
        }
    
        for (long i = 1; i <= nrows_freq; ++i) {
            int freqid;
            fits_read_col(in_fptr, TINT, colnum_freqid, i, 1, 1, NULL, &freqid, NULL, &status);
    
            // Get the number of BANDFREQ values for this FREQID
            long nbandfreq = 0; // Use long for nbandfreq
            fits_get_coltype(in_fptr, colnum_bandfreq, NULL, &nbandfreq, NULL, &status);
            if (status) {
            std::cerr << "Error after nbandfreq = " << status << std::endl;
            fits_report_error(stderr, status);
            fits_close_file(in_fptr, &status);
            return results;
            }
    
            freqidToBandfreq[freqid] = nbandfreq;
        }

        for (int hdu_num = 1; hdu_num <= num_hdus; hdu_num++) {                                     // iterate through each HDU
            int hdu_type;
            fits_movabs_hdu(in_fptr, hdu_num, &hdu_type, &status);                                  // move hdu pointer to hdu_num
            print_fits_error(status);
            

            char hdu_name[FLEN_VALUE];                                                              // hdu name
            fits_read_key(in_fptr, TSTRING, "EXTNAME", hdu_name, NULL, &status);
            if (status == KEY_NO_EXIST) {                                                           // handle empty hdu
                status = 0;
                strcpy(hdu_name, "");
            }
            print_fits_error(status);

            if (strcmp(hdu_name, "UV_DATA") == 0) {                                             // UV_DATA operations start
                
                long nrows;
                fits_get_num_rows(in_fptr, &nrows, &status);

                
                // std::cout << "Processing HDU: " << hdu_name << " (HDU #" << hdu_num << "), nrows: " << nrows << std::endl;
                int colnum_time, colnum_source, colnum_inttim, colnum_freqid;
                
                fits_get_colnum(in_fptr, CASEINSEN, timeColName, &colnum_time, &status);
                fits_get_colnum(in_fptr, CASEINSEN, sourceColName, &colnum_source, &status);
                fits_get_colnum(in_fptr, CASEINSEN, inttimColName, &colnum_inttim, &status);
                fits_get_colnum(in_fptr, CASEINSEN, freqidColName, &colnum_freqid, &status);
                if (status) {
                std::cerr << "Error getting colnum_inttim = " << status << std::endl;
                        fits_report_error(stderr, status);
                        fits_close_file(in_fptr, &status);
                        return results;
                    }

                for (long i = 1; i <= nrows; ++i) {
                    double time;
                    double inttime;
                    int source, freqid;
                    fits_read_col(in_fptr, TDOUBLE, colnum_time, i, 1, 1, NULL, &time, NULL, &status);
                    fits_read_col(in_fptr, TINT, colnum_source, i, 1, 1, NULL, &source, NULL, &status);
                    fits_read_col(in_fptr, TDOUBLE, colnum_inttim, i, 1, 1, NULL, &inttime, NULL, &status);
                    fits_read_col(in_fptr, TINT, colnum_freqid, i, 1, 1, NULL, &freqid, NULL, &status);
            
                    if (status) {
                        // std::cout << freqid << " " << colnum_freqid << " "<<colnum_source << "\n";
                        std::cout << freqid << " " << colnum_freqid << " "<<colnum_source << "\n";
                        std::cerr << "Error after freqid = " << status << std::endl;
                        fits_report_error(stderr, status);
                        fits_close_file(in_fptr, &status);
                        return results;
                    }
            
                    // Skip rows where SOURCE is not in sids (if sids is not empty)
                    if (filter_by_sids && sids_set.find(source) == sids_set.end()) {
                        continue;
                    }
            
                    // Calculate the absolute MJD timestamp
                    double scantime_mjd = time;
            
                    // If the SOURCE changes, save the previous SOURCE's data
                    if (source != current_source) {
                        if (current_source != -1) {
                            // Get the number of BANDFREQ values for the current FREQID
                            long nbandfreq = (freqidToBandfreq.find(current_freqid) != freqidToBandfreq.end()) ? freqidToBandfreq[current_freqid] : 1;
            
                            // Create the inttime array (e.g., "[1.0 1.0 1.0 1.0]")
                            std::vector<double> inttimeArray;
                            for (long j = 0; j < nbandfreq; ++j) {
                                inttimeArray.push_back(current_inttime);
                            }
            
                            // Convert MJD to ISOT for start and end times
                            double startTime = current_time_start_mjd;//convertMJDToISOT(current_time_start_mjd);
                            double endTime = current_time_end_mjd;//convertMJDToISOT(current_time_end_mjd);
            
                            // Save the previous SOURCE's data
                            results.push_back({
                                startTime,
                                endTime,
                                current_source,
                                current_nrows,
                                inttimeArray
                            });
                        }
                        // Start tracking the new SOURCE
                        current_source = source;
                        current_time_start_mjd = scantime_mjd;
                        current_time_end_mjd = scantime_mjd;
                        current_nrows = 1;
                        current_freqid = freqid;
                        current_inttime = inttime; // Update current_inttime
                    } 
                    else {
                        // Update the end time and increment nrows for the current SOURCE
                        current_time_end_mjd = scantime_mjd;
                        current_nrows++;

                    }

                }

                if (current_source != -1) {
                    
                    long nbandfreq = freqidToBandfreq[current_freqid];
            
                    // Create the inttime array (e.g., "[1.0 1.0 1.0 1.0]")
                    std::vector<double> inttimeArray;
                    for (long j = 0; j < nbandfreq; ++j) {
                        inttimeArray.push_back(current_inttime);
                    }
                    // inttimeArray << "[";
                    // for (long j = 0; j < nbandfreq; ++j) {
                    //     if (j > 0) inttimeArray << " ";
                    //     inttimeArray << current_inttime; // Use the actual inttime value
                    // }
                    // inttimeArray << "]";

                    double startTime = current_time_start_mjd;
                    double endTime = current_time_end_mjd;
            
                    results.push_back({
                        startTime,
                        endTime,
                        current_source,
                        current_nrows,
                        inttimeArray
                    });
                    current_source = -1;
                }
                
                if (status) {
            std::cerr << "Error after close = " << status << std::endl;
                    fits_report_error(stderr, status);
                    fits_close_file(in_fptr, &status);
                    return results;
                }
            }
        }
        
        fits_close_file(in_fptr, &status);
        return results;
    }
};

#endif