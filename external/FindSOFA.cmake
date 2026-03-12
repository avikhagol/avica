# Find the SOFA library
# Defines the following variables:
#   SOFA_FOUND        - True if SOFA is found
#   SOFA_INCLUDE_DIR  - Directory containing sofa.h
#   SOFA_LIBRARY      - The SOFA library

find_path(SOFA_INCLUDE_DIR
  NAMES sofa.h
  PATH_SUFFIXES sofa
)

find_library(SOFA_LIBRARY
  NAMES sofa
)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(SOFA DEFAULT_MSG SOFA_LIBRARY SOFA_INCLUDE_DIR)

mark_as_advanced(SOFA_INCLUDE_DIR SOFA_LIBRARY)