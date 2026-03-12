#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "fitsidi_lib.h"
#include "fitsidi_listobs.h"

namespace py = pybind11;

PYBIND11_MODULE (_core, m){
    m.doc() = "Pybind11 wrapper for FitsIDIUtil C++";

    py::class_<RowData>(m, "RowData")
        .def(py::init<>())  // Default constructor
        .def_readwrite("time_start", &RowData::time_start)
        .def_readwrite("time_end", &RowData::time_end)
        .def_readwrite("source", &RowData::source)
        .def_readwrite("nrows", &RowData::nrows)
        .def_readwrite("inttime", &RowData::inttime);

        m.def("listobs", [](const std::string& fitsfilepath, const std::optional<std::vector<long int>>& sids) {
            std::vector<long int> sids_vec = sids.value_or(std::vector<long int>{});
            return ListObs::listobs_fits(fitsfilepath, sids_vec);
        }, 
        py::arg("fitsfilepath"), py::arg("sids") = py::none(), 
        "Process a FITS file and return observation data.");

    m.def("split", [](
        const std::string& fitsfilepath, const std::string& outfitsfilepath, 
        const std::optional <std::vector<long int>>& sids, 
        const std::optional <std::vector<long int>>& baseline_ids,
        const std::optional<std::vector<long int>>& freqids,
        const std::string& source_col,
        const std::string& baseline_col,
        const std::string& frequency_col,
        const std::string& expression,
        const bool reindex,
        const bool verbose = true
    ) {
        std::vector<long int> sids_vec = sids.value_or(std::vector<long int>{});
        std::vector<long int> baseline_ids_vec = baseline_ids.value_or(std::vector<long int>{});
        std::vector<long int> freqids_vec = freqids.value_or(std::vector<long int>{});
        
        return SplitSources::split(fitsfilepath, outfitsfilepath, sids_vec, baseline_ids_vec, freqids_vec,
            source_col, baseline_col, frequency_col, expression, reindex, verbose
        );
        }, 
        py::arg("fitsfilepath"), py::arg("outfitsfilepath"),
       py::arg("sids") = py::none(), py::arg("baseline_ids") = py::none(), py::arg("freqids") = py::none(),
       py::arg("source_col") = "SOURCE", py::arg("baseline_col") = "BASELINE", 
       py::arg("frequency_col") = "FREQID",
       py::arg("expression") = "", 
       py::arg("reindex") = false,
       py::arg("verbose") = true,
       "Split a FITS file based on source and baseline IDs.");

   m.def("rm_hdr", &delete_hdu,
          py::arg("fitsfilepath"), py::arg("hdu_index"),
          "Delete an HDU from a FITS file by index.");
}