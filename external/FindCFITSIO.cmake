# Locate the CFITSIO library
# This script defines:
#   FITSIO_FOUND        - True if CFITSIO is found
#   FITSIO_INCLUDE_DIR  - Directory containing fitsio.h
#   FITSIO_LIBRARY      - The CFITSIO library
#   FITSIO_LIBRARIES    - Library variable for linking
#   FITSIO_INCLUDE_DIRS - Include directory variable for use in targets

find_path(FITSIO_INCLUDE_DIR
  NAMES fitsio.h
  PATH_SUFFIXES fitsio
  # HINTS ${CMAKE_PREFIX_PATH}/include /usr/include /usr/local/include
)

find_library(FITSIO_LIBRARY
  NAMES cfitsio fitsio
  # HINTS ${CMAKE_PREFIX_PATH}/lib /usr/lib /usr/local/lib
)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(FITSIO DEFAULT_MSG FITSIO_LIBRARY FITSIO_INCLUDE_DIR)

if(FITSIO_FOUND)
  set(FITSIO_LIBRARIES ${FITSIO_LIBRARY})
  set(FITSIO_INCLUDE_DIRS ${FITSIO_INCLUDE_DIR})
endif()

mark_as_advanced(FITSIO_INCLUDE_DIR FITSIO_LIBRARY)
