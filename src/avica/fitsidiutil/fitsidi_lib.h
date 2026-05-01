#ifndef FITSIDI_LIB
#define FITSIDI_LIB

#include <string>
#include <set>
#include <iostream>
#include <vector>
#include "fitsio.h"
#include <cstring>
#include <map>
#include <utility>
#include <fstream>
#include <sstream>
#include <iomanip>

// ----------- Process Data

class SplitSources {
    public:
        static void print_fits_error(int status) {
            if (status) {
                fits_report_error(stderr, status);
                exit(status);
            }
        }
        
        static int split(
                        const std::string& fitsfilepath, const std::string& outfitsfilepath,
                        const std::vector<long int>* sids = nullptr,
                        const std::vector<long int>* baseline_ids = nullptr,
                        const std::vector<long int>* freqids = nullptr,
                        const std::string& source_col = "SOURCE",
                        const std::string& baseline_col = "BASELINE",
                        const std::string& frequency_col = "FREQID",
                        const std::string& expression = "",
                        const bool reindex = false,
                        const bool verbose = true
                    )
                {

                    const char *input_fits_filename = fitsfilepath.c_str();
                    const char *output_fits_filename = outfitsfilepath.c_str();
                    std::vector<long int> sids_vec         = sids         ? *sids         : std::vector<long int>{};
                    std::vector<long int> baseline_ids_vec = baseline_ids ? *baseline_ids : std::vector<long int>{};
                    std::vector<long int> freqids_vec      = freqids      ? *freqids      : std::vector<long int>{};
                
                    fitsfile *in_fptr, *out_fptr;
                    int status = 0, colnum_source, colnum_baseline, anynul;
                    long nrows;
                    int ncols;
                    int num_hdus;
                    const char *source_colname = source_col.c_str();
                    const char *baseline_colname = baseline_col.c_str();
                    const char *frequency_colname = frequency_col.c_str();
                    std::string expr = expression;
                    bool multiexpr = false;
                
                    fits_open_file(&in_fptr, input_fits_filename, READONLY, &status);                           // open the input FITS file
                    print_fits_error(status);
                
                    fits_create_file(&out_fptr, output_fits_filename, &status);                                 // create a new fits
                    print_fits_error(status);
                
                    
                    fits_get_num_hdus(in_fptr, &num_hdus, &status);
                    print_fits_error(status);
                    int multi_uv_data_colnum =0;
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
                
                        if (hdu_type == IMAGE_HDU) {                                                            // starts copying
                            fits_copy_hdu(in_fptr, out_fptr, 0, &status);
                            print_fits_error(status);
                        } else if (hdu_type == BINARY_TBL || hdu_type == ASCII_TBL) {
                            if (strcmp(hdu_name, "UV_DATA") == 0) {
                                ++multi_uv_data_colnum;

                                std::string sccol = source_colname;
                                std::string bscol = baseline_col;
                                std::string fqcol = frequency_col;
                                
                                if (!freqids_vec.empty()) {
                                    if (!expr.empty()) {
                                        expr = "(" + expr + ") && (";
                                        multiexpr = true;
                                    }
                                    expr += fqcol + " == " + std::to_string(freqids_vec[0]);
                                    
                                    for (size_t i = 1; i < freqids_vec.size(); i++) {
                                        expr += " || " + fqcol + " == " + std::to_string(freqids_vec[i]);
                                    }
                                    if (!expr.empty() && multiexpr) {
                                        expr += ")";
                                    }
                                }
                                if (!sids_vec.empty()) {
                                    if (!expr.empty()) {
                                        expr = "(" + expr + ") && (";
                                        multiexpr = true;
                                    }
                                    expr += sccol + " == " + std::to_string(sids_vec[0]);

                                    for (size_t i = 1; i < sids_vec.size(); i++) {
                                        expr += " || " + sccol + " == " + std::to_string(sids_vec[i]);
                                    }
                                    if (!expr.empty() && multiexpr) {
                                        expr += ")";
                                    }
                                }
                                if (!baseline_ids_vec.empty()) {
                                        if (!expr.empty()) {
                                            expr = "(" + expr + ") && (";
                                            multiexpr = true;
                                        }
                                        expr += bscol + " == " + std::to_string(baseline_ids_vec[0]);
                                        
                                        for (size_t i = 1; i < baseline_ids_vec.size(); i++) {
                                            expr += " || " + bscol + " == " + std::to_string(baseline_ids_vec[i]);
                                        }
                                        
                                        if (!expr.empty() && multiexpr) {
                                            expr += ")";
                                        }
                                }
                                if (!expr.empty()) {
                                 
                                    fits_get_num_cols(in_fptr, &ncols, &status);
                                    print_fits_error(status);
                                    
                                    char *ttype[ncols], *tform[ncols], *tunit[ncols];                               // arrays for column names, formats, and units
                                    for (int col = 0; col < ncols; col++) {
                                        ttype[col] = new char[FLEN_VALUE];
                                        tform[col] = new char[FLEN_VALUE];
                                        tunit[col] = new char[FLEN_VALUE];
                    
                                        fits_get_bcolparms(in_fptr, col + 1, ttype[col], NULL, tunit[col], NULL, NULL, NULL, NULL, NULL, &status);
                                        print_fits_error(status);
                    
                                        int col_type;
                                        long repeat, width;
                                        fits_get_coltype(in_fptr, col + 1, &col_type, &repeat, &width, &status);    // column data type => map to TFORM
                                        print_fits_error(status);
                        
                                        if (repeat == 0) {
                                            if (verbose){
                                                std::cerr <<"HDU#"<<multi_uv_data_colnum << ": Skipping column " << col + 1 << " (" << ttype[col] << ") with invalid TFORM value.\n";
                                            }
                                            snprintf(tform[col], FLEN_VALUE, "0J");                                 // check 0J for invalid
                                        } else {
                                            switch (col_type) {
                                                case TLONG:
                                                    snprintf(tform[col], FLEN_VALUE, "%ldJ", repeat);
                                                    break;
                                                case TDOUBLE:
                                                    snprintf(tform[col], FLEN_VALUE, "%ldD", repeat);
                                                    break;
                                                case TFLOAT:
                                                    snprintf(tform[col], FLEN_VALUE, "%ldE", repeat);
                                                    break;
                                                case TSTRING:
                                                    snprintf(tform[col], FLEN_VALUE, "%ldA", width);
                                                    break;
                                                default:
                                                    std::cerr <<"HDU#"<<multi_uv_data_colnum << ": Unsupported column type for column " << col + 1 << "\n";
                                                    exit(1);
                                            }
                                        }
                                    }

                                    fits_create_tbl(out_fptr, BINARY_TBL, 0, ncols, ttype, tform, tunit, 
                                        "UV_DATA", &status);
                                    print_fits_error(status);

                                    fits_select_rows(in_fptr, out_fptr, const_cast<char*>(expr.c_str()), &status);
                                    print_fits_error(status);
                                    
                                    long selected_rows;
                                    fits_get_num_rows(out_fptr, &selected_rows, &status);
                                    print_fits_error(status);
                                    
                                    if (verbose){
                                        std::cout << "HDU#" << hdu_num << ": Selected " << selected_rows 
                                            << " rows with expression: " << expr << std::endl;
                                    }
                                } 
                                else {
                                    
                                    fits_copy_hdu(in_fptr, out_fptr, 0, &status);
                                    print_fits_error(status);
                                }
                            } 
                            else {
                                fits_copy_hdu(in_fptr, out_fptr, 0, &status);   // other columns
                                print_fits_error(status);
                            }
                        }
                    }
                    
                    
                    fits_close_file(in_fptr, &status);  
                    print_fits_error(status);
                    fits_close_file(out_fptr, &status);
                    print_fits_error(status);
                
                    return 0;
                }



};


std::string format_fits_card(std::string key, std::string value, std::string comm) {
    std::stringstream ss;
    ss << std::left << std::setw(8) << key.substr(0, 8);
    ss << "= ";
    ss << std::setw(20) << value;
    ss << " / " << comm;
    
    std::string card = ss.str();
    if (card.length() > 80) return card.substr(0, 80);
    return card + std::string(80 - card.length(), ' ');
}

void write_key(std::string filep, int pos, std::string key, std::string value, std::string comm) {
    std::fstream file(filep, std::ios::in | std::ios::out | std::ios::binary); // writes in the pos and shifts
    if (!file) return;

    std::vector<char> original_block(2880);
    file.read(original_block.data(), 2880);

    std::string new_card = format_fits_card(key, value, comm);
    
    int offset = (pos - 1) * 80;

    std::vector<char> repaired_block;
    repaired_block.reserve(2880);
    repaired_block.insert(repaired_block.end(), original_block.begin(), original_block.begin() + offset);
    repaired_block.insert(repaired_block.end(), new_card.begin(), new_card.end());
    repaired_block.insert(repaired_block.end(), original_block.begin() + offset, original_block.begin() + (2880 - 80));

    file.seekp(0);
    file.write(repaired_block.data(), 2880);
    file.close();
}

void repair_key(std::string filep, int pos, std::string key, std::string value, std::string comm) {
    std::fstream file(filep, std::ios::in | std::ios::out | std::ios::binary);  // write in the pos without shifting
    if (!file) return;

    int offset = (pos - 1) * 80;
    
    std::string new_card = format_fits_card(key, value, comm);

    file.seekp(offset);
    file.write(new_card.c_str(), 80);
    file.close();
}

void repair_hdu_key(std::string filep, int hdu_num, int card_pos, 
                     std::string key, long value, std::string comm, bool shift) {
    fitsfile* fptr;
    int status = 0;
    
    fits_open_data(&fptr, filep.c_str(), READWRITE, &status);
    if (status) status = 0; 

    fits_movabs_hdu(fptr, hdu_num, NULL, &status);

    if (shift) {
        char kname[72], kval[72];
        fits_read_keyn(fptr, card_pos - 1, kname, kval, NULL, &status);
        fits_insert_key_lng(fptr, key.c_str(), value, comm.c_str(), &status);
    } else {
        fits_update_key_lng(fptr, key.c_str(), value, comm.c_str(), &status);
    }

    fits_close_file(fptr, &status);
}



#endif
