#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace schgen {

struct CatalogPin {
    std::string number;
    std::string name;
    std::string etype;
};

struct CatalogPart {
    std::string mpn;
    std::string safe_name;
    std::string lcsc;
    std::string description;
    std::string manufacturer;
    std::string package;
    std::string jlc_class;
    std::string prefix;
    std::string datasheet;
    std::string product_url;
    std::string lib_id;
    std::string footprint;
    std::vector<std::string> models_3d;
    std::vector<CatalogPin> pins;
};

bool compile_part_catalog(const std::string& parts_dir,
                          const std::string& catalog_path);
bool open_part_catalog(const std::string& catalog_path);
bool close_part_catalog();
CatalogPart lookup_part_catalog(const std::string& mpn);
std::size_t part_catalog_count();

}  // namespace schgen
