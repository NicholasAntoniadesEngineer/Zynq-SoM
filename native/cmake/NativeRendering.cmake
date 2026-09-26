include_guard(GLOBAL)
find_path(SCHGEN_POPPLER_INCLUDE_DIR poppler/cpp/poppler-document.h
    HINTS /opt/homebrew/include /usr/local/include REQUIRED)
find_library(SCHGEN_POPPLER_CPP_LIBRARY NAMES poppler-cpp
    HINTS /opt/homebrew/lib /usr/local/lib REQUIRED)
find_package(PNG 1.6 REQUIRED)
add_library(schgen_poppler_cpp UNKNOWN IMPORTED)
set_target_properties(schgen_poppler_cpp PROPERTIES
    IMPORTED_LOCATION "${SCHGEN_POPPLER_CPP_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${SCHGEN_POPPLER_INCLUDE_DIR}")
