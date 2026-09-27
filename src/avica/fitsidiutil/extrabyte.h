#include <fitsio.h>
#include <sys/stat.h>
#include <string>

/**
 * Returns the number of extra bytes.
 * Returns 0 if the file is clean OR if an error occurs (to avoid crashing).
 * You can check 'status' to see if a CFITSIO error actually happened.
 */
long long get_extra_bytes(const std::string& fitsfilepath) {
    fitsfile *fptr;
    int status = 0; // CFITSIO error code
    int num_hdus = 0;
    long long headstart, datastart, dataend;

    struct stat st;
    if (stat(fitsfilepath.c_str(), &st) != 0) {
        return 0;
    }
    long long actual_size = st.st_size;

    if (fits_open_file(&fptr, fitsfilepath.c_str(), READONLY, &status)) {
        return 0;
    }

    fits_get_num_hdus(fptr, &num_hdus, &status);
    fits_movabs_hdu(fptr, num_hdus, NULL, &status);
    
    fits_get_hduaddrll(fptr, &headstart, &datastart, &dataend, &status);
    
    fits_close_file(fptr, &status);


    if (status > 0) {
        return 0;
    }


    long long remainder = dataend % 2880;
    long long expected_size = dataend;
    if (remainder > 0) {
        expected_size += (2880 - remainder);
    }

    return actual_size - expected_size;
}

int main() {
    return 0;
}