
#include <iostream>
#include <iomanip>
#include <vector>
#include <string>
#include <algorithm>
#include <fstream>
#include <sstream>
#include <iomanip>

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
    std::fstream file(filep, std::ios::in | std::ios::out | std::ios::binary);
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
    std::fstream file(filep, std::ios::in | std::ios::out | std::ios::binary);
    if (!file) return;

    int offset = (pos - 1) * 80;
    
    std::string new_card = format_fits_card(key, value, comm);

    file.seekp(offset);
    file.write(new_card.c_str(), 80);
    file.close();
}

int main() {

    std::string path = "/home/avi/intelligence/gh/vasco/tests/tes2.fits";
    

    std::cout << "--- Starting Repair ---" << std::endl;
    
    
    repair_naxis(path);

    // std::cout << "--- Attempting Standard Open ---" << std::endl;
    
    // // Now the standard open should work
    // if (io.open(path, true)) {
    //     std::cout << "✅ Success! File is now valid." << std::endl;
    //     io.fetch_header();
    //     std::cout << "HDUs found: " << io.header_mgr.all_hdus.size() << std::endl;
    //     io.close();
    // } else {
    //     std::cerr << "❌ Open still failing after repair." << std::endl;
    // }

    return 0;
}