#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "fitsidi_lib.h"
#include "fitsidi_io.h"

namespace py = pybind11;

PYBIND11_MODULE (_core, m){
    m.doc() = "Pybind11 wrapper for FitsIDIUtil C++";

    py::class_<HeaderCard>(m, "HeaderCard")
        .def(py::init<>()) 
        .def_readwrite("key", &HeaderCard::key)
        .def_readwrite("value", &HeaderCard::value)
        .def_readwrite("comment", &HeaderCard::comment)
        .def_readwrite("type", &HeaderCard::type);

    py::class_<HeaderManager>(m, "HeaderManager")
        .def(py::init<>())
        .def("load_all", &HeaderManager::load_all)
        .def_readonly("all_hdus", &HeaderManager::all_hdus)
        .def_readonly("history", &HeaderManager::history)
        .def_readonly("comments", &HeaderManager::comments);

    py::class_<RowData>(m, "RowData")
        .def(py::init<>())  // Default constructor
        .def_readwrite("time_start", &RowData::time_start)
        .def_readwrite("time_end", &RowData::time_end)
        .def_readwrite("source", &RowData::source)
        .def_readwrite("nrows", &RowData::nrows)
        .def_readwrite("inttime", &RowData::inttime);

    py::class_<ReadIO>(m, "ReadIO")
        .def(py::init<>())
        .def("open", &ReadIO::open, py::arg("fitsfilepath"), py::arg("writeable") = false)
        .def("close", &ReadIO::close)
        .def("flush", &ReadIO::flush)
        .def("fetch_header", &ReadIO::fetch_header)
        .def_readwrite("header_mgr", &ReadIO::header_mgr)
        .def("update_header_str", &ReadIO::update_header_str, 
            py::arg("hdu_num"), py::arg("key"), py::arg("value"), py::arg("comment"),
                "update key, value in header where value is str")
        .def("update_header_int", &ReadIO::update_header_int, 
            py::arg("hdu_num"), py::arg("key"), py::arg("value"), py::arg("comment"),
                "update key, value in header where value is int")
        .def("update_header_double", &ReadIO::update_header_double, 
            py::arg("hdu_num"), py::arg("key"), py::arg("value"), py::arg("comment"),
                "update key, value in header where value is double")
        .def("insert_header_after", &ReadIO::insert_header_after, 
            py::arg("hdu_num"), py::arg("after_key"), py::arg("key"), 
            py::arg("value"), py::arg("comment"), py::arg("dtype"),
            "Insert header keyword after another keyword with specified dtype")
        .def("insert_header", &ReadIO::insert_header, 
            py::arg("hdu_num"), py::arg("position"), py::arg("key"), 
            py::arg("value"), py::arg("comment"), py::arg("dtype"),
            "Insert header keyword at position with specified dtype")
        .def("insert_header_str_after", &ReadIO::insert_header_str_after, 
            py::arg("hdu_num"), py::arg("after_key"), py::arg("key"), py::arg("value"), py::arg("comment"),
            "insert key, value in header where value is str")
        .def("insert_header_int_after", &ReadIO::insert_header_int_after, 
            py::arg("hdu_num"), py::arg("after_key"), py::arg("key"), py::arg("value"), py::arg("comment"),
            "insert key, value in header where value is int")
        .def("insert_header_double_after", &ReadIO::insert_header_double_after, 
            py::arg("hdu_num"), py::arg("after_key"), py::arg("key"), py::arg("value"), py::arg("comment"),
            "insert key, value in header where value is double")
        .def("insert_header_str", &ReadIO::insert_header_str, 
            py::arg("hdu_num"), py::arg("position"), py::arg("key"), py::arg("value"), py::arg("comment"),
            "insert key, value in header where value is str")
        .def("insert_header_int", &ReadIO::insert_header_int, 
            py::arg("hdu_num"), py::arg("position"), py::arg("key"), py::arg("value"), py::arg("comment"),
            "insert key, value in header where value is int")
        .def("insert_header_double", &ReadIO::insert_header_double, 
            py::arg("hdu_num"), py::arg("position"), py::arg("key"), py::arg("value"), py::arg("comment"),
            "insert key, value in header where value is double")
        .def("save_as", &ReadIO::save_as,
            py::arg("outfitsfilepath"),
            py::arg("uv_data_dict_by_hdu") = py::none(),
            py::arg("verbose")      = false,
            "Writes a new FITS file using streaming and Python edits")
        .def("write_table_column", &ReadIO::write_table_column,
            py::arg("hdu_num"), py::arg("colname"), py::arg("data"), py::arg("start_row")=0,
                "update table data in place")
        .def("delete_header_key", &ReadIO::delete_header_key, 
            py::arg("hdu_num"), py::arg("key"),
                "delete requested key")
        // .def("read_as_dict", &ReadIO::read_table_as_numpy, "Read HDU directly into NumPy arrays")
        .def("read_table_chunked", &ReadIO::read_table_chunked, "Read HDU directly into NumPy arrays by chunk")
        .def("listobs", &ReadIO::listobs_fits, 
            py::arg("sids") = py::none(), 
                "Get observation data from the currently open file")
        .def("delete_hdu", &ReadIO::delete_hdu,
            py::arg("hdu_num"),
                "Delete an HDU from a FITS file by index.")
        .def("get_fits_byte_size", &ReadIO::get_fits_byte_size, 
                "Returns (actual_size, expected_size).")
        .def("read_hdutable", &ReadIO::read_table_by_hdu, 
            py::arg("hdu_num"), 
                "Read a specific HDU table as a list of lists");


    m.def("split", [](
    const std::string& fitsfilepath, const std::string& outfitsfilepath, 
    py::object sids,
    py::object baseline_ids,
    py::object freqids,
    const std::string& source_col,
    const std::string& baseline_col,
    const std::string& frequency_col,
    const std::string& expression,
    const bool reindex,
    const bool verbose
    ) {
        std::vector<long int> sids_vec         = sids.is_none()         ? std::vector<long int>{} : sids.cast<std::vector<long int>>();
        std::vector<long int> baseline_ids_vec = baseline_ids.is_none() ? std::vector<long int>{} : baseline_ids.cast<std::vector<long int>>();
        std::vector<long int> freqids_vec      = freqids.is_none()      ? std::vector<long int>{} : freqids.cast<std::vector<long int>>();
        
        return SplitSources::split(fitsfilepath, outfitsfilepath, &sids_vec, &baseline_ids_vec, &freqids_vec,
            source_col, baseline_col, frequency_col, expression, reindex, verbose);
    },
    py::arg("fitsfilepath"),
    py::arg("outfitsfilepath"),
    py::arg("sids")         = py::none(),
    py::arg("baseline_ids") = py::none(),
    py::arg("freqids")      = py::none(),
    py::arg("source_col")   = "SOURCE",
    py::arg("baseline_col") = "BASELINE",
    py::arg("frequency_col")= "FREQID",
    py::arg("expression")   = "",
    py::arg("reindex")      = false,
    py::arg("verbose")      = true
);

    m.def("repair_hdu_key", &repair_hdu_key, 
          "Repair or insert a key. If shift=True, it inserts and pushes data down. "
          "If shift=False, it updates/overwrites by key name.",
          py::arg("filep"), 
          py::arg("hdu_num"), 
          py::arg("card_pos"), 
          py::arg("key"), 
          py::arg("value"), 
          py::arg("comm"),
          py::arg("shift") = true); // Default to true for safety

}