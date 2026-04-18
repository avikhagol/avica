cmake_minimum_required(VERSION 3.18...3.30)
option(BUILD_SHARED_LIBS "Build shared libraries" OFF)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(CMAKE_POSITION_INDEPENDENT_CODE ON CACHE BOOL "" FORCE)

project(${SKBUILD_PROJECT_NAME} LANGUAGES CXX VERSION ${SKBUILD_PROJECT_VERSION})

set_property(GLOBAL PROPERTY JOB_POOLS one_jobs=4 two_jobs=8)

include(FetchContent)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 17)
set(CFITSIO_VERSION 4.5.0)

if(DEFINED ENV{VIRTUAL_ENV})
    set(Python3_EXECUTABLE "$ENV{VIRTUAL_ENV}/bin/python3")
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)

set(PYBIND11_NEWPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

# Fetch CFITSIO
set(USE_CURL     OFF CACHE BOOL "" FORCE)
set(USE_PTHREADS OFF CACHE BOOL "" FORCE)
set(SKIP_INSTALL_ALL ON CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(CFITSIO_SKIP_PROGRAMS ON CACHE BOOL "" FORCE)
FetchContent_Declare(cfitsio URL https://github.com/HEASARC/cfitsio/archive/refs/tags/cfitsio-${CFITSIO_VERSION}.tar.gz)
FetchContent_MakeAvailable(cfitsio)

if(NOT TARGET cfitsio)
    message(FATAL_ERROR "cfitsio target not found after FetchContent")
endif()

get_target_property(_type cfitsio TYPE)
message(STATUS "cfitsio TYPE: ${_type}")
set_target_properties(cfitsio PROPERTIES POSITION_INDEPENDENT_CODE ON JOB_POOL_COMPILE one_jobs JOB_POOL_LINK one_jobs)


# Build Executable
set(FITSIDIUTIL_MODULE _core)
pybind11_add_module(${FITSIDIUTIL_MODULE} MODULE src/vasco/fitsidiutil/bindings.cpp)
set_target_properties(${FITSIDIUTIL_MODULE} PROPERTIES OUTPUT_NAME _core JOB_POOL_COMPILE one_jobs JOB_POOL_LINK two_jobs)
target_link_libraries(${FITSIDIUTIL_MODULE} PRIVATE $<TARGET_FILE:cfitsio> Python3::Module)
target_include_directories(${FITSIDIUTIL_MODULE} PRIVATE ${cfitsio_SOURCE_DIR} ${cfitsio_SOURCE_DIR}/include)

install(TARGETS ${FITSIDIUTIL_MODULE}
    LIBRARY DESTINATION ${SKBUILD_PROJECT_NAME}/fitsidiutil
    RUNTIME DESTINATION ${SKBUILD_PROJECT_NAME}/fitsidiutil
)

# --------  DEBUG   -------------------------------------------------------------------
# add_custom_command(TARGET ${FITSIDIUTIL_MODULE} POST_BUILD
#     COMMAND sh -c "nm -D $<TARGET_FILE:${FITSIDIUTIL_MODULE}> | grep GLIBC | sort -u"
#     VERBATIM
#     COMMENT "Checking GLIBC symbols"
# )