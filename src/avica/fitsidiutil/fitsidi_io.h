#ifndef FITSIDI_IO
#define FITSIDI_IO
#include <iostream>
#include <vector>
#include <map>
#include <iomanip>
#include <cmath>
#include "fitsio.h"
#include <set>
#include <cstring>
#include <string>
#include <cstdio>

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
namespace py = pybind11;


static void print_fits_error(int status) {
    if (status) {
        fits_report_error(stderr, status);
        exit(status);
    }
}


// ----------- Read Header

struct HeaderCard {
    std::string key;
    std::string value;
    std::string comment;
    int type;
};

class HeaderManager {
public:
    fitsfile* fptr = nullptr;
    std::map<int, std::vector<HeaderCard>> all_hdus;

    std::map<int, std::vector<std::string>> history;
    std::map<int, std::vector<std::string>> comments;

    ~HeaderManager() {
        close_file();
    }

    void close_file() {
        if (fptr) {
            int status = 0;
            fits_close_file(fptr, &status);
            fptr = nullptr;
        }
    }

    void load_all() {   // loads all headers
            int status = 0;
            int num_hdus = 0;
            char key[FLEN_KEYWORD], val[FLEN_VALUE], com[FLEN_COMMENT];

            fits_get_num_hdus(fptr, &num_hdus, &status);

            for (int hdu_num = 1; hdu_num <= num_hdus; hdu_num++) {
                int nkeys = 0;
                int keytype = 0;

                if (fits_movabs_hdu(fptr, hdu_num, NULL, &status)) {
                    status = 0;
                    continue;
                }


                fits_get_hdrspace(fptr, &nkeys, NULL, &status);

                std::vector<HeaderCard> current_hdu_cards;

                for (int i = 1; i <= nkeys; i++) {
                        if (fits_read_keyn(fptr, i, key, val, com, &status)) {
                            status = 0;
                            continue;
                        }

                        char letter_type[FLEN_VALUE];
                        fits_get_keytype(val, letter_type, &status);
                        int key_code = (int)letter_type[0];

                        if (status) {
                            key_code = 0;
                            status = 0;
                        }


                        std::string s_key = key;
                        if (s_key == "HISTORY") {
                            history[hdu_num].push_back(com);
                        } else if (s_key == "COMMENT") {
                            comments[hdu_num].push_back(com);
                        } else if (s_key != "CONTINUE" && s_key != "END" && !s_key.empty()) {

                            current_hdu_cards.push_back({s_key, val, com, key_code});
                        }
                    }
                all_hdus[hdu_num] = current_hdu_cards;
            }

        }
};



struct RowData {                //  used by listobs to read time, source, nrows
    double time_start;
    double time_end;
    int source;
    long nrows;
    std::vector<double> inttime;
};

typedef struct RowData Struct;

class ReadIO {
    private:
        fitsfile *fptr = nullptr;
        int status = 0;
        std::string _current_fitsfilepath;

        int ascii_code_to_cfitsio_dtype(int ascii_code) {
                switch(ascii_code) {
                    case 73:  // 'I' - ASCII for 'I'
                        return TINT;      // 41
                    case 70:  // 'F' - ASCII for 'F'
                        return TDOUBLE;   // 82 (or TFLOAT=42 if you prefer)
                    case 67:  // 'C' - ASCII for 'C'
                        return TSTRING;   // 43
                    case 76:  // 'L' - ASCII for 'L'
                        return TLOGICAL;  // 14
                    case 88:  // 'X' - ASCII for 'X' (complex)
                        return TCOMPLEX;  // 84
                    default:
                        return TSTRING;   // default to string
                }
            }

    public:
        HeaderManager header_mgr;


        bool open(const std::string& fitsfilepath, bool writeable = false) {
            _current_fitsfilepath = fitsfilepath;

            this->status = 0;
            int mode = writeable ? READWRITE : READONLY;
            const char* filename = fitsfilepath.c_str();
            fits_open_file(&fptr, filename, mode, &status);
            if (status) {
                std::cerr << "Error after open = " << status << std::endl;
                            fits_report_error(stderr, status);
                            return false;
                        }
            header_mgr.fptr = fptr;
            return true;
        }

        std::map<int, std::vector<HeaderCard>> fetch_header(){
            if (fptr) {
                header_mgr.load_all();
            }
            return header_mgr.all_hdus;
        }

        void close() {
            if (this->fptr) {
                int closing_stat = 0;
                fits_close_file(this->fptr, &closing_stat);

                this->fptr = nullptr;
                this->header_mgr.fptr = nullptr;
                this->status = 0;
            }
        }
        void flush() {
            if (fptr) {
                int status = 0;
                fits_flush_file(fptr, &status);

                if (status) {
                    char err_text[80];
                    fits_get_errstatus(status, err_text);
                    throw std::runtime_error("CFITSIO Flush Error: " + std::string(err_text));
                }
            }
        }

        ~ReadIO() {
            close();
        }

        // ---------------- header updates
        void update_header_str(int hdu_num, std::string key, std::string value, std::string comment) {
            int status = 0, hdu_type;
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_update_key(fptr, TSTRING, key.c_str(), (void*)value.c_str(), comment.c_str(), &status);
        }

        void update_header_double(int hdu_num, std::string key, double value, std::string comment) {
            int status = 0, hdu_type;
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_update_key(fptr, TDOUBLE, key.c_str(), &value, comment.c_str(), &status);
        }

        void update_header_int(int hdu_num, std::string key, long value, std::string comment) {
            int status = 0, hdu_type;
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_update_key(fptr, TLONG, key.c_str(), &value, comment.c_str(), &status);
        }
        void delete_header_key(int hdu_num, const std::string& key) {
            int status = 0;
            fits_movabs_hdu(fptr, hdu_num, nullptr, &status);
            fits_delete_key(fptr, key.c_str(), &status);
            if (status != 0) {
                print_fits_error(status);
                status = 0;
            }
        }

        // -------------------- insert header after

        void insert_header_str_after(int hdu_num, const std::string& after_key, const std::string& key, const std::string& value, const std::string& comment) {
            int status = 0, hdu_type;
            char card[FLEN_CARD];  // raw 80-char card
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_read_card(fptr, after_key.c_str(), card, &status);
            fits_insert_key_str(fptr, key.c_str(), value.c_str(), comment.c_str(), &status);
            if (status != 0) { print_fits_error(status); }
        }

        void insert_header_double_after(int hdu_num, const std::string& after_key, const std::string& key, double value, const std::string& comment) {
            int status = 0, hdu_type;
            char card[FLEN_CARD];
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_read_card(fptr, after_key.c_str(), card, &status);
            fits_insert_key_dbl(fptr, key.c_str(), value, -15, comment.c_str(), &status);
            if (status != 0) { print_fits_error(status); }
        }

        void insert_header_int_after(int hdu_num, const std::string& after_key, const std::string& key, long value, const std::string& comment) {
            int status = 0, hdu_type;
            char card[FLEN_CARD];
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_read_card(fptr, after_key.c_str(), card, &status);
            fits_insert_key_lng(fptr, key.c_str(), value, comment.c_str(), &status);
            if (status != 0) { print_fits_error(status); }
        }

        // -------------------- add new headers
        void insert_header_str(int hdu_num, int position, std::string key, std::string value, std::string comment) {
            int status = 0, hdu_type;
            char keyname[FLEN_KEYWORD], val[FLEN_VALUE], comm[FLEN_COMMENT];
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_read_keyn(fptr, position, keyname, val, comm, &status);
            fits_insert_key_str(fptr, key.c_str(), value.c_str(), comment.c_str(), &status);
            if (status != 0) { print_fits_error(status); }
        }

        void insert_header_double(int hdu_num, int position, std::string key, double value, std::string comment) {
            int status = 0, hdu_type;
            char keyname[FLEN_KEYWORD], val[FLEN_VALUE], comm[FLEN_COMMENT];
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_read_keyn(fptr, position, keyname, val, comm, &status);
            fits_insert_key_dbl(fptr, key.c_str(), value, -15, comment.c_str(), &status);
            if (status != 0) { print_fits_error(status); }
        }

        void insert_header_int(int hdu_num, int position, std::string key, long value, std::string comment) {
            int status = 0, hdu_type;
            char keyname[FLEN_KEYWORD], val[FLEN_VALUE], comm[FLEN_COMMENT];
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_read_keyn(fptr, position, keyname, val, comm, &status);
            fits_insert_key_lng(fptr, key.c_str(), value, comment.c_str(), &status);
            if (status != 0) { print_fits_error(status); }
        }


        // one func for header updaes

        void insert_header_after(int hdu_num, const std::string& after_key, const std::string& key,
                         const std::string& value, const std::string& comment, int dtype) {
            int status = 0, hdu_type;
            char card[FLEN_CARD];
            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
            fits_read_card(fptr, after_key.c_str(), card, &status);

            int cfitsio_dtype = ascii_code_to_cfitsio_dtype(dtype);

            switch(cfitsio_dtype) {
                case TINT:
                case TLOGICAL: {
                    long val = std::stol(value);
                    fits_update_key(fptr, TLONG, key.c_str(), &val, comment.c_str(), &status);
                    break;
                }
                case TDOUBLE:
                case TFLOAT: {
                    double val = std::stod(value);
                    fits_update_key(fptr, TDOUBLE, key.c_str(), &val, comment.c_str(), &status);
                    break;
                }
                case TSTRING:
                default: {
                    fits_update_key(fptr, TSTRING, key.c_str(), (void*)value.c_str(), comment.c_str(), &status);
                    break;
                }
            }
            if (status != 0) { print_fits_error(status); }
        }

            void insert_header(int hdu_num, int position, const std::string& key,
                const std::string& value, const std::string& comment, int dtype) {
                int status = 0, hdu_type;
                char keyname[FLEN_KEYWORD], val[FLEN_VALUE], comm[FLEN_COMMENT];
                fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
                fits_read_keyn(fptr, position, keyname, val, comm, &status);

                int cfitsio_dtype = ascii_code_to_cfitsio_dtype(dtype);

                switch(cfitsio_dtype) {
                    case TINT:
                    case TLOGICAL: {
                        long long_val = std::stol(value);
                        fits_update_key(fptr, TLONG, key.c_str(), &long_val, comment.c_str(), &status);
                        break;
                    }
                    case TDOUBLE:
                    case TFLOAT: {
                        double double_val = std::stod(value);
                        fits_update_key(fptr, TDOUBLE, key.c_str(), &double_val, comment.c_str(), &status);
                        break;
                    }
                    case TSTRING:
                    default: {
                        fits_update_key(fptr, TSTRING, key.c_str(), (void*)value.c_str(), comment.c_str(), &status);
                        break;
                    }
                }
                if (status != 0) { print_fits_error(status); }
            }

        // -------------------- update Data

        // fits write

        void write_python_dict_to_table(fitsfile* out_ptr, py::dict data, int* status) {
            if (data.size() == 0 || *status) return;

            // --- row count from first column ---
            auto first_item = *data.begin();
            py::object first_col = py::reinterpret_borrow<py::object>(first_item.second);
            long num_rows = (long)py::len(first_col);
            if (num_rows == 0) return;

            fits_insert_rows(out_ptr, 0, num_rows, status);
            if (*status) {
                fits_report_error(stderr, *status);
                throw std::runtime_error("fits_insert_rows failed");
            }

            for (auto item : data) {
                std::string colname = item.first.cast<std::string>();
                py::object  col_data = py::reinterpret_borrow<py::object>(item.second);

                int col_num = 0;
                int col_status = 0;
                fits_get_colnum(out_ptr, CASEINSEN, const_cast<char*>(colname.c_str()),
                                &col_num, &col_status);
                if (col_status) {
                    std::cerr << "skipping unknown column '"
                            << colname << "'\n";
                    continue;
                }

                int  typecode = 0;
                long repeat   = 0;
                long width    = 0;
                fits_get_coltype(out_ptr, col_num, &typecode, &repeat, &width, status);
                if (*status) {
                    fits_report_error(stderr, *status);
                    throw std::runtime_error("fits_get_coltype failed for '"
                                            + colname + "'");
                }
                int abs_type = std::abs(typecode);

                //-----------------------------------------------------------------------------
                if (abs_type == TSTRING) {
                    if (!py::isinstance<py::list>(col_data))
                        throw std::runtime_error("column '"
                                                + colname + "' is TSTRING but data is not a list");

                    py::list lst = col_data.cast<py::list>();
                    for (long r = 0; r < num_rows; ++r) {
                        std::string val;
                        if (py::isinstance<py::bytes>(lst[r]))
                            val = lst[r].cast<std::string>();
                        else
                            val = py::str(lst[r]).cast<std::string>();

                        char* valptr[1] = { const_cast<char*>(val.c_str()) };
                        fits_write_col_str(out_ptr, col_num, r + 1, 1, 1, valptr, status);
                        if (*status) {
                            fits_report_error(stderr, *status);
                            throw std::runtime_error("string write failed at row "
                                                    + std::to_string(r + 1) + " col '" + colname + "'");
                        }
                    }
                    continue;
                }

                // ----------------------------------------------------------------
                if (repeat == 1) {
                    if (abs_type == TDOUBLE || abs_type == TFLOAT) {
                        auto arr = col_data.cast<py::array_t<double, py::array::c_style | py::array::forcecast>>();
                        if ((long)arr.size() != num_rows)
                            throw std::runtime_error("row count mismatch for '"
                                                    + colname + "'");
                        fits_write_col(out_ptr, TDOUBLE, col_num, 1, 1, num_rows,
                                    const_cast<void*>(static_cast<const void*>(arr.data())), status);
                    }
                    else if (abs_type == TINT   || abs_type == TLONG  ||
                            abs_type == TSHORT || abs_type == TBYTE  ||
                            abs_type == TINT32BIT) {
                        auto arr = col_data.cast<py::array_t<long, py::array::c_style | py::array::forcecast>>();
                        if ((long)arr.size() != num_rows)
                            throw std::runtime_error("row count mismatch for '"
                                                    + colname + "'");
                        fits_write_col(out_ptr, TLONG, col_num, 1, 1, num_rows,
                                    const_cast<void*>(static_cast<const void*>(arr.data())), status);
                    }
                    else {
                        throw std::runtime_error("unsupported scalar type "
                                                + std::to_string(abs_type) + " for '" + colname + "'");
                    }

                    if (*status) {
                        fits_report_error(stderr, *status);
                        throw std::runtime_error("scalar write failed for '"
                                                + colname + "'");
                    }
                    continue;
                }

                // ----------------------------------------------------------------
                if (repeat > 1) {
                    auto arr = col_data.cast<py::array_t<double, py::array::c_style | py::array::forcecast>>();

                    long total_elements = num_rows * repeat;
                    if ((long)arr.size() != total_elements)
                        throw std::runtime_error("array element count mismatch for '"
                                                + colname + "' — expected "
                                                + std::to_string(total_elements) + " got "
                                                + std::to_string(arr.size()));

                    fits_write_col(out_ptr, TDOUBLE, col_num, 1, 1, total_elements,
                                const_cast<void*>(static_cast<const void*>(arr.data())), status);

                    if (*status) {
                        fits_report_error(stderr, *status);
                        throw std::runtime_error("array write failed for '"
                                                + colname + "'");
                    }
                    continue;
                }

                std::cerr << "skipping column '" << colname
                        << "' with repeat=0\n";
            }
        }

        int save_as(const std::string& outfitsfilepath,
                py::object uv_data_dict_by_hdu = py::none(),
                bool verbose = false) {

                if (!fptr) throw std::runtime_error("No FITS file is currently open.");

                fitsfile* out_fptr = nullptr;
                int status = 0;
                int num_hdus = 0;
                const std::string safe_out = "!" + outfitsfilepath;

                bool has_override = !uv_data_dict_by_hdu.is_none();

                fits_create_file(&out_fptr, safe_out.c_str(), &status);
                if (status) {
                    fits_report_error(stderr, status);
                    throw std::runtime_error("save_as: could not create: " + outfitsfilepath);
                }

                fits_get_num_hdus(fptr, &num_hdus, &status);
                print_fits_error(status);

                int uv_data_counter = 0;

                for (int hdu_num = 1; hdu_num <= num_hdus; ++hdu_num) {
                    int hdu_type = 0;
                    fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);
                    print_fits_error(status);

                    char hdu_name[FLEN_VALUE] = {0};
                    int key_status = 0;
                    fits_read_key(fptr, TSTRING, "EXTNAME", hdu_name, NULL, &key_status);
                    if (key_status) { key_status = 0; std::strcpy(hdu_name, ""); }

                    bool is_uv_data = (std::strcmp(hdu_name, "UV_DATA") == 0);

                    if (!is_uv_data || !has_override) {
                        fits_copy_hdu(fptr, out_fptr, 0, &status);
                        print_fits_error(status);
                        if (verbose)
                            std::cout << "save_as: copied HDU #" << hdu_num
                                    << " (" << (*hdu_name ? hdu_name : "—") << ")\n";
                        continue;
                    }

                    py::dict uv_dict;
                    bool use_override = false;

                    if (has_override) {
                        py::dict override_dict = uv_data_dict_by_hdu.cast<py::dict>();
                        py::object key = py::int_(uv_data_counter);

                        if (override_dict.contains(key)) {
                            uv_dict = override_dict[key].cast<py::dict>();
                            use_override = true;
                            if (verbose) {
                                std::cout << "Using override for UV_DATA #" << uv_data_counter << std::endl;
                            }
                        }
                    }

                    if (!use_override) {
                        // copy original
                        fits_copy_hdu(fptr, out_fptr, 0, &status);
                        print_fits_error(status);
                        if (verbose) {
                            std::cout << "Copying UV_DATA #" << uv_data_counter << " unchanged\n";
                        }
                        uv_data_counter++;
                        continue;
                    }

                    int ncols = 0;
                    fits_get_num_cols(fptr, &ncols, &status);
                    print_fits_error(status);

                    std::vector<char*> ttype(ncols), tform(ncols), tunit(ncols);
                    for (int col = 0; col < ncols; ++col) {
                        ttype[col] = new char[FLEN_VALUE];
                        tform[col] = new char[FLEN_VALUE];
                        tunit[col] = new char[FLEN_VALUE];

                        fits_get_bcolparms(fptr, col + 1, ttype[col], NULL,
                                        tunit[col], NULL, NULL, NULL, NULL, NULL, &status);
                        print_fits_error(status);

                        int col_type;
                        long repeat, width;
                        fits_get_coltype(fptr, col + 1, &col_type, &repeat, &width, &status);
                        print_fits_error(status);

                        if (repeat == 0) {
                            std::snprintf(tform[col], FLEN_VALUE, "0J");
                        } else {
                            switch (std::abs(col_type)) {
                                case TLONG:   std::snprintf(tform[col], FLEN_VALUE, "%ldJ", repeat); break;
                                case TDOUBLE: std::snprintf(tform[col], FLEN_VALUE, "%ldD", repeat); break;
                                case TFLOAT:  std::snprintf(tform[col], FLEN_VALUE, "%ldE", repeat); break;
                                case TSTRING: std::snprintf(tform[col], FLEN_VALUE, "%ldA", width); break;
                                default:
                                    for (int i = 0; i <= col; ++i) delete[] ttype[i];
                                    fits_close_file(out_fptr, &status);
                                    throw std::runtime_error("save_as: unsupported column type at col "
                                                            + std::to_string(col + 1));
                            }
                        }
                    }

                    fits_create_tbl(out_fptr, BINARY_TBL, 0, ncols, ttype.data(), tform.data(), tunit.data(), "UV_DATA", &status);
                    print_fits_error(status);
                    // fits_copy_header(fptr, out_fptr, &status);   // this creates undesired new hdu

                    long reset_rows = 0;
                    fits_modify_key_lng(out_fptr, "NAXIS2", reset_rows, NULL, &status);

                    write_python_dict_to_table(out_fptr, uv_dict, &status);
                    print_fits_error(status);

                    for (int col = 0; col < ncols; ++col) {
                        delete[] ttype[col];
                        delete[] tform[col];
                        delete[] tunit[col];
                    }

                    if (verbose) {
                        long written = 0;
                        fits_get_num_rows(out_fptr, &written, &status);
                        std::cout << "save_as: UV_DATA #" << uv_data_counter
                                << " — wrote " << written << " filtered rows\n";
                    }

                    uv_data_counter++;
                }

                fits_close_file(out_fptr, &status);
                print_fits_error(status);
                return 0;
            }


        // table write
        void write_table_column(int hdu_num, std::string colname, py::object data, long start_row = 0) {
                if (!fptr) throw std::runtime_error("No FITS file is currently open.");

                int local_status = 0;
                int hdu_type;

                fits_movabs_hdu(fptr, hdu_num, &hdu_type, &local_status);
                if (local_status || (hdu_type != BINARY_TBL && hdu_type != ASCII_TBL)) {
                    throw std::runtime_error("HDU " + std::to_string(hdu_num) + " is not a valid Table.");
                }

                int colnum;
                fits_get_colnum(fptr, CASEINSEN, (char*)colname.c_str(), &colnum, &local_status);
                if (local_status) {
                    local_status = 0;
                    throw std::runtime_error("Column '" + colname + "' not found in HDU " + std::to_string(hdu_num));
                }

                int typecode;
                long repeat, width;
                fits_get_coltype(fptr, colnum, &typecode, &repeat, &width, &local_status);
                int abs_type = abs(typecode);

                // --- TSTRING
                if (abs_type == TSTRING) {
                    if (!py::isinstance<py::list>(data))
                        throw std::runtime_error("String column update requires a Python list.");

                    py::list list_data = data.cast<py::list>();
                    for (long i = 0; i < list_data.size(); ++i) {
                        std::string val;

                        if (py::isinstance<py::bytes>(list_data[i])) {
                            val = list_data[i].cast<std::string>();
                        } else {
                            val = py::str(list_data[i]).cast<std::string>();
                        }

                        char *valptr[1] = {(char*)val.c_str()};

                        fits_write_col_str(fptr, colnum, start_row + i + 1, 1, 1, valptr, &local_status);
                    }
                }

                // --- scalars, arrays
                else {
                    if (abs_type == TDOUBLE || abs_type == TFLOAT) {
                        auto arr = data.cast<py::array_t<double>>();
                        fits_write_col(fptr, TDOUBLE, colnum, start_row + 1, 1, arr.size(), (void*)arr.data(), &local_status);
                    }
                    else if (abs_type == TINT || abs_type == TLONG || abs_type == TSHORT || abs_type == TBYTE || abs_type == TINT32BIT) {
                        auto arr = data.cast<py::array_t<long>>();
                        fits_write_col(fptr, TLONG, colnum, start_row + 1, 1, arr.size(), (void*)arr.data(), &local_status);
                    }
                    else {
                        throw std::runtime_error("Unsupported FITS data type for column update: " + std::to_string(abs_type));
                    }
                }


                if (local_status) {
                    char err_text[FLEN_ERRMSG];
                    fits_get_errstatus(local_status, err_text);
                    local_status = 0;
                    throw std::runtime_error("CFITSIO Write Error [" + colname + "]: " + std::string(err_text));
                }
            }
        py::dict read_table_chunked(int hdu_num, long start_row, long end_row) {
            py::dict result;
            if (!fptr) return result;

            int local_status = 0;
            int hdu_type;

            fits_movabs_hdu(fptr, hdu_num, &hdu_type, &local_status);
            if (local_status || (hdu_type != BINARY_TBL && hdu_type != ASCII_TBL)) {
                return result;
            }

            long total_rows;
            fits_get_num_rows(fptr, &total_rows, &local_status);
            if (start_row < 0) start_row = 0;
            if (end_row >= total_rows) end_row = total_rows - 1;

            long num_rows_to_read = end_row - start_row + 1;
            if (num_rows_to_read <= 0) return result;

            int ncols;
            fits_get_num_cols(fptr, &ncols, &local_status);

            for (int col = 1; col <= ncols; col++) {
                char colname[FLEN_VALUE] = {0};
                int typecode;
                long repeat, width;
                char keyname[FLEN_KEYWORD];
                snprintf(keyname, sizeof(keyname), "TTYPE%d", col);
                fits_read_key(fptr, TSTRING, keyname, colname, NULL, &local_status);
                if (local_status) {
                    local_status = 0;
                    snprintf(colname, sizeof(colname), "COL%d", col);
                }

                fits_get_coltype(fptr, col, &typecode, &repeat, &width, &local_status);
                int abs_type = abs(typecode);

                if (abs_type == TSTRING) {
                    std::vector<std::vector<unsigned char>> raw_rows(num_rows_to_read,
                                                                     std::vector<unsigned char>(width, 0));
                    bool any_dirty = false;

                    for (long r = 0; r < num_rows_to_read; ++r) {
                        local_status = 0;
                        fits_read_col(fptr, TBYTE, col, start_row + r + 1, 1, width,
                                      NULL, raw_rows[r].data(), NULL, &local_status);

                        const auto& raw = raw_rows[r];
                        auto null_it = std::find(raw.begin(), raw.end(), '\0');
                        size_t name_len = null_it - raw.begin();

                        // tail garbage after \0
                        for (size_t i = name_len; i < (size_t)width; ++i) {
                            if (raw[i] != '\0') { any_dirty = true; break; }
                        }
                        if (!any_dirty) {
                            for (size_t i = 0; i < name_len; ++i) {
                                unsigned char c = raw[i];
                                if (c < 0x20 || c > 0x7e) { any_dirty = true; break; }
                            }
                        }
                    }

                    py::list out;
                    if (any_dirty) {
                            for (long r = 0; r < num_rows_to_read; ++r) {
                                out.append(py::bytes(reinterpret_cast<const char*>(raw_rows[r].data()), width));
                            }
                        } else {
                            for (long r = 0; r < num_rows_to_read; ++r) {
                                const auto& raw = raw_rows[r];
                                auto null_it = std::find(raw.begin(), raw.end(), '\0');
                                size_t name_len = null_it - raw.begin();
                                std::string s(reinterpret_cast<const char*>(raw.data()), name_len);
                                size_t last = s.find_last_not_of(" \n\r\t");
                                s = (last != std::string::npos) ? s.substr(0, last + 1) : "";
                                out.append(py::str(s));
                            }
                        }
                        result[colname] = out;
                    }
                else if (repeat == 1) {
                    if (abs_type == TDOUBLE || abs_type == TFLOAT) {
                        py::array_t<double> arr(num_rows_to_read);
                        fits_read_col(fptr, TDOUBLE, col, start_row + 1, 1, num_rows_to_read, NULL, arr.mutable_data(), NULL, &local_status);
                        result[colname] = arr;
                    }
                    else if (abs_type == TINT || abs_type == TLONG || abs_type == TSHORT || abs_type == TBYTE) {
                        py::array_t<long> arr(num_rows_to_read);
                        fits_read_col(fptr, TLONG, col, start_row + 1, 1, num_rows_to_read, NULL, arr.mutable_data(), NULL, &local_status);
                        result[colname] = arr;
                    }
                }
                else if (repeat > 1) {
                    py::array_t<double> arr({(size_t)num_rows_to_read, (size_t)repeat});
                    fits_read_col(fptr, TDOUBLE, col, start_row + 1, 1, num_rows_to_read * repeat, NULL, arr.mutable_data(), NULL, &local_status);
                    result[colname] = arr;
                }

                local_status = 0;
            }
            return result;
        }

    std::vector<std::vector<std::string>> read_table_by_hdu(int hdu_num) {
        std::vector<std::vector<std::string>> table_data;
        if (!fptr) return table_data;

        int local_status = 0;
        int hdu_type;

        fits_movabs_hdu(fptr, hdu_num, &hdu_type, &local_status);
        if (local_status || (hdu_type != BINARY_TBL && hdu_type != ASCII_TBL)) {
            return table_data;
        }

        long nrows;
        int ncols;
        fits_get_num_rows(fptr, &nrows, &local_status);
        fits_get_num_cols(fptr, &ncols, &local_status);

        if (local_status || nrows <= 0) return table_data;


        std::vector<int> col_types(ncols);
        std::vector<long> col_repeats(ncols);
        std::vector<long> col_widths(ncols);

        for (int col = 0; col < ncols; col++) {
            fits_get_coltype(fptr, col + 1, &col_types[col], &col_repeats[col], &col_widths[col], &local_status);
        }

        table_data.reserve(nrows);

        for (long row = 1; row <= nrows; row++) {
            std::vector<std::string> row_data;
            row_data.reserve(ncols);

            for (int col = 0; col < ncols; col++) {
                local_status = 0;
                int type = abs(col_types[col]);

                if (col_repeats[col] > 1 && type != TSTRING) {
                    std::string arr_str = "[";

                    if (type == TDOUBLE || type == TFLOAT) {
                        std::vector<double> vals(col_repeats[col]);
                        fits_read_col(fptr, TDOUBLE, col + 1, row, 1, col_repeats[col], NULL, vals.data(), NULL, &local_status);
                        for (size_t i = 0; i < vals.size(); i++) {
                            char n_buf[64];
                            snprintf(n_buf, sizeof(n_buf), "%.10g", vals[i]);
                            arr_str += (i > 0 ? ", " : "") + std::string(n_buf);
                        }
                    }
                    else if (type == TINT || type == TLONG || type == TSHORT || type == TBYTE) {
                        std::vector<long> vals(col_repeats[col]);
                        fits_read_col(fptr, TLONG, col + 1, row, 1, col_repeats[col], NULL, vals.data(), NULL, &local_status);
                        for (size_t i = 0; i < vals.size(); i++) {
                            arr_str += (i > 0 ? ", " : "") + std::to_string(vals[i]);
                        }
                    }

                    arr_str += "]";
                    row_data.push_back(local_status ? "[ERROR]" : arr_str);
                }
                else {
                    char buffer[FLEN_VALUE] = {0};

                    if (type == TSTRING) {
                        char *str_ptr = buffer;
                        if (fits_read_col(fptr, TSTRING, col + 1, row, 1, 1, NULL, &str_ptr, NULL, &local_status) == 0) {
                            std::string s(buffer);
                            size_t last = s.find_last_not_of(' ');
                            row_data.push_back((last == std::string::npos) ? "" : s.substr(0, last + 1));
                        } else {
                            row_data.push_back("");
                        }
                    }
                    else if (type == TDOUBLE || type == TFLOAT) {
                        double val;
                        fits_read_col(fptr, TDOUBLE, col + 1, row, 1, 1, NULL, &val, NULL, &local_status);
                        snprintf(buffer, sizeof(buffer), "%.10f", val);
                        row_data.push_back(local_status ? "0.0" : buffer);
                    }
                    else if (type == TINT || type == TLONG || type == TSHORT || type == TBYTE) {
                        long val;
                        fits_read_col(fptr, TLONG, col + 1, row, 1, 1, NULL, &val, NULL, &local_status);
                        row_data.push_back(local_status ? "0" : std::to_string(val));
                    }
                    else {
                        row_data.push_back("");
                    }
                }
                local_status = 0;
            }
            table_data.push_back(row_data);
        }

        return table_data;
    }
        std::vector<RowData> listobs_fits(py::object sids_arg = py::none())
            {
            std::vector<long int> sids_vec;
            bool filter_by_sids = false;

            if (!sids_arg.is_none()) {
                sids_vec = sids_arg.cast<std::vector<long int>>();
                filter_by_sids = !sids_vec.empty();
            }

            int num_hdus;
            int status = 0;
            std::map<int, long> freqidToBandfreq;

            std::vector<RowData> results;
            std::set<long int> sids_set(sids_vec.begin(), sids_vec.end());
            if (!fptr) return results;


            fits_get_num_hdus(fptr, &num_hdus, &status);                                             // get number of hdus
            print_fits_error(status);
            int current_source = -1;
            double current_time_start_mjd = 0.0, current_time_end_mjd = 0.0;
            long current_nrows = 0;
            int current_freqid = -1;
            double current_inttime = 0.0;
            char timeColName[] = "TIME";
            char sourceColName[] = "SOURCE";
            char inttimColName[] = "INTTIM";
            char freqidColName[] = "FREQID";

            char frequencyHduName[] = "FREQUENCY";
            fits_movnam_hdu(fptr, BINARY_TBL, frequencyHduName, 0, &status);
            if (status) {
                std::cerr << "Error after status moving FREQ = " << status << std::endl;
                fits_report_error(stderr, status);

                return results;
            }
            int colnum_freqid;
            fits_get_colnum(fptr, CASEINSEN, freqidColName, &colnum_freqid, &status);
            if (status) {
                std::cerr << "Error after freqidColName  = " << status << std::endl;
                fits_report_error(stderr, status);

                return results;
            }
            int colnum_bandfreq;
            char bandfreqColName[] = "BANDFREQ";
            fits_get_colnum(fptr, CASEINSEN, bandfreqColName, &colnum_bandfreq, &status);
            if (status) {
                std::cerr << "Error after bandfreqColName = " << status << std::endl;
                fits_report_error(stderr, status);

                return results;
            }

            long nrows_freq;
            fits_get_num_rows(fptr, &nrows_freq, &status);
            if (status) {
                std::cerr << "Error after nrows_freq  = " << status << std::endl;
                fits_report_error(stderr, status);

                return results;
            }

            for (long i = 1; i <= nrows_freq; ++i) {
                int freqid;
                fits_read_col(fptr, TINT, colnum_freqid, i, 1, 1, NULL, &freqid, NULL, &status);

                // get the number of BANDFREQ values for this FREQID
                long nbandfreq = 0;
                fits_get_coltype(fptr, colnum_bandfreq, NULL, &nbandfreq, NULL, &status);
                if (status) {
                std::cerr << "Error after nbandfreq = " << status << std::endl;
                fits_report_error(stderr, status);

                return results;
                }

                freqidToBandfreq[freqid] = nbandfreq;
            }

            for (int hdu_num = 1; hdu_num <= num_hdus; hdu_num++) {                                     // iterate through each HDU
                int hdu_type;
                fits_movabs_hdu(fptr, hdu_num, &hdu_type, &status);                                  // move hdu pointer to hdu_num
                print_fits_error(status);


                char hdu_name[FLEN_VALUE];                                                              // hdu name
                fits_read_key(fptr, TSTRING, "EXTNAME", hdu_name, NULL, &status);
                if (status == KEY_NO_EXIST) {                                                           // handle empty hdu
                    status = 0;
                    strcpy(hdu_name, "");
                }
                print_fits_error(status);

                if (strcmp(hdu_name, "UV_DATA") == 0) {                                             // UV_DATA operations start

                    long nrows;
                    fits_get_num_rows(fptr, &nrows, &status);


                    // std::cout << "Processing HDU: " << hdu_name << " (HDU #" << hdu_num << "), nrows: " << nrows << std::endl;
                    int colnum_time, colnum_source, colnum_inttim, colnum_freqid;

                    fits_get_colnum(fptr, CASEINSEN, timeColName, &colnum_time, &status);
                    fits_get_colnum(fptr, CASEINSEN, sourceColName, &colnum_source, &status);
                    fits_get_colnum(fptr, CASEINSEN, inttimColName, &colnum_inttim, &status);
                    fits_get_colnum(fptr, CASEINSEN, freqidColName, &colnum_freqid, &status);
                    if (status) {
                    std::cerr << "Error getting colnum_inttim = " << status << std::endl;
                            fits_report_error(stderr, status);

                            return results;
                        }

                    for (long i = 1; i <= nrows; ++i) {
                        double time;
                        double inttime;
                        int source, freqid;
                        fits_read_col(fptr, TDOUBLE, colnum_time, i, 1, 1, NULL, &time, NULL, &status);
                        fits_read_col(fptr, TINT, colnum_source, i, 1, 1, NULL, &source, NULL, &status);
                        fits_read_col(fptr, TDOUBLE, colnum_inttim, i, 1, 1, NULL, &inttime, NULL, &status);
                        fits_read_col(fptr, TINT, colnum_freqid, i, 1, 1, NULL, &freqid, NULL, &status);

                        if (status) {
                            // std::cout << freqid << " " << colnum_freqid << " "<<colnum_source << "\n";
                            std::cout << freqid << " " << colnum_freqid << " "<<colnum_source << "\n";
                            std::cerr << "Error after freqid = " << status << std::endl;
                            fits_report_error(stderr, status);

                            return results;
                        }

                        if (filter_by_sids && sids_set.find(source) == sids_set.end()) {
                            continue;
                        }

                        double scantime_mjd = time;

                        if (source != current_source) {
                            if (current_source != -1) {

                                long nbandfreq = (freqidToBandfreq.find(current_freqid) != freqidToBandfreq.end()) ? freqidToBandfreq[current_freqid] : 1;

                                std::vector<double> inttimeArray;
                                for (long j = 0; j < nbandfreq; ++j) {
                                    inttimeArray.push_back(current_inttime);
                                }

                                double startTime = current_time_start_mjd;//convertMJDToISOT(current_time_start_mjd);
                                double endTime = current_time_end_mjd;//convertMJDToISOT(current_time_end_mjd);


                                results.push_back({
                                    startTime,
                                    endTime,
                                    current_source,
                                    current_nrows,
                                    inttimeArray
                                });
                            }

                            current_source = source;
                            current_time_start_mjd = scantime_mjd;
                            current_time_end_mjd = scantime_mjd;
                            current_nrows = 1;
                            current_freqid = freqid;
                            current_inttime = inttime; // Update current_inttime
                        }
                        else {
                            current_time_end_mjd = scantime_mjd;
                            current_nrows++;

                        }

                    }

                    if (current_source != -1) {

                        long nbandfreq = freqidToBandfreq[current_freqid];

                        std::vector<double> inttimeArray;
                        for (long j = 0; j < nbandfreq; ++j) {
                            inttimeArray.push_back(current_inttime);
                        }
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

                        return results;
                    }
                }
            }


            return results;
        }


    void delete_hdu(int hdu_num) {
        int status = 0, hdutype;
        if (fits_movabs_hdu(fptr, hdu_num, &hdutype, &status)) {
            fits_report_error(stderr, status);
            fits_close_file(fptr, &status);
            return;
        }

        if (fits_delete_hdu(fptr, &hdutype, &status)) {
            fits_report_error(stderr, status);
        }

    }


    std::pair<long long, long long> get_fits_byte_size() {

        int status = 0;
        int num_hdus = 0;
        long long headstart, datastart, dataend;

        struct stat st;
        if (stat(_current_fitsfilepath.c_str(), &st) != 0) {
            return {0, 0};
        }
        long long actual_size = st.st_size;


        fits_get_num_hdus(fptr, &num_hdus, &status);
        fits_movabs_hdu(fptr, num_hdus, NULL, &status);

        fits_get_hduaddrll(fptr, &headstart, &datastart, &dataend, &status);


        if (status > 0) {
            return {actual_size, 0};
        }


        long long remainder = dataend % 2880;
        long long expected_size = dataend;
        if (remainder > 0) {
            expected_size += (2880 - remainder);
        }

        return {actual_size, expected_size};
        }

    };

#endif