cmake_minimum_required(VERSION 3.18...3.30)
project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX VERSION ${SKBUILD_PROJECT_VERSION})
option(BUILD_SHARED_LIBS "Build using shared libraries" ON)

# Set job pools to limit parallel jobs
set_property(GLOBAL PROPERTY JOB_POOLS one_jobs=4 two_jobs=8)

# Check available physical memory
cmake_host_system_information(RESULT _memfree QUERY AVAILABLE_PHYSICAL_MEMORY)

# set(PYBIND11_NEWPYTHON ON)
include(FetchContent)
set(CMAKE_CXX_STANDARD 17)

# set versions
set(CFITSIO_VERSION 4.5.0)

# Python3
if(DEFINED ENV{VIRTUAL_ENV})
    set(Python3_EXECUTABLE "$ENV{VIRTUAL_ENV}/bin/python3")
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

# pybind11
# execute_process(COMMAND ${Python3_EXECUTABLE} -c "import pybind11; print(pybind11.get_cmake_dir())" OUTPUT_VARIABLE pybind11_DIR OUTPUT_STRIP_TRAILING_WHITESPACE) #for manual
set(PYBIND11_NEWPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

# CFITSIO
FetchContent_Declare(cfitsio URL https://github.com/HEASARC/cfitsio/archive/refs/tags/cfitsio-${CFITSIO_VERSION}.tar.gz)
FetchContent_MakeAvailable(cfitsio)
find_package(PkgConfig REQUIRED)
pkg_check_modules(CFITSIO REQUIRED IMPORTED_TARGET cfitsio)

# Build Executable
set(FITSIDIUTIL_MODULE _core)
pybind11_add_module(${FITSIDIUTIL_MODULE} MODULE src/vasco/fitsidiutil/bindings.cpp)

set_target_properties(${FITSIDIUTIL_MODULE} PROPERTIES 
    OUTPUT_NAME _core
)

set_target_properties(${FITSIDIUTIL_MODULE} PROPERTIES 
    JOB_POOL_COMPILE one_jobs
    JOB_POOL_LINK two_jobs
)

# Set job pool for the module if memory is low
if(_memfree LESS 4096)
    set_property(TARGET ${FITSIDIUTIL_MODULE} PROPERTY JOB_POOL_COMPILE one_jobs)
endif()

# set(CMAKE_BUILD_RPATH ${ORIGIN})
message(STATUS "CFITSIO target exists: ${CFITSIO_LIBRARIES} ${cfitsio_SOURCE_DIR} ${cfitsio_DIR} ${cfitsio_BUILD} ${ORGIN}")
if(NOT TARGET cfitsio::cfitsio)
    message(FATAL_ERROR "cfitsio::cfitsio is not a TARGET")
endif()

set_target_properties(${FITSIDIUTIL_MODULE} PROPERTIES INSTALL_RPATH "\$ORIGIN:\$ORIGIN/../lib/:\$ORIGIN/../lib64/")

target_link_libraries(${FITSIDIUTIL_MODULE} PRIVATE cfitsio::cfitsio Python3::Python)
target_include_directories(${FITSIDIUTIL_MODULE} PRIVATE ${cfitsio_SOURCE_DIR} ${sofa_SRC})
install(TARGETS ${FITSIDIUTIL_MODULE} 
        LIBRARY DESTINATION ${SKBUILD_PROJECT_NAME}/fitsidiutil
        RUNTIME DESTINATION ${SKBUILD_PROJECT_NAME}/fitsidiutil)