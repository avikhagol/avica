# Find the PYBIND11 library
# Defines the following variables:
#   PYBIND11_FOUND        - True if PYBIND11 is found
#   PYBIND11_INCLUDE_DIR  - Directory containing pybind11.h
#   PYBIND11_LIBRARY      - The PYBIND11 library

find_path(PYBIND11_INCLUDE_DIR
  NAMES pybind11.h
  PATH_SUFFIXES pybind11
)

find_library(PYBIND11_LIBRARY
  NAMES pybind11
)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(PYBIND11 DEFAULT_MSG PYBIND11_LIBRARY PYBIND11_INCLUDE_DIR)

mark_as_advanced(PYBIND11_INCLUDE_DIR PYBIND11_LIBRARY)