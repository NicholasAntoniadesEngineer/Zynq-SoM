#pragma once
#include "schgen/board_schematic.hpp"
#include "schgen/project.hpp"
#include <algorithm>
#include <iostream>
#include <unistd.h>

namespace schgen::test {
// Keep current IR and extracted KiCad connectivity on the same revision.
// Scratch is private and retained for failure diagnosis; repository outputs
// are never overwritten. This uses real authoring and netlist gates, not a
// netlist synthesized from the ownership declarations being tested.
inline std::filesystem::path fresh_project_schematic(const ProjectPaths& paths,
        const std::vector<ProjectCircuit>& circuits) {
    auto pattern=(std::filesystem::temp_directory_path()/"schgen-current-input.XXXXXX").string();
    const auto created=::mkdtemp(pattern.data());
    if(!created)throw std::runtime_error("cannot create private schematic scratch");
    const std::filesystem::path scratch=created;
    std::cout<<"current schematic scratch="<<scratch<<'\n';
    const auto index=load_sheet_index(paths);
    std::vector<BoardSheetInput> inputs;
    for(const auto& circuit:circuits) {
        const auto band=std::find_if(index.begin(),index.end(),[&](const auto& row){return row.first==circuit.name;});
        if(band==index.end())throw std::runtime_error("missing persistent sheet reference band");
        inputs.push_back({circuit.circuit,band->second,std::nullopt});
    }
    SymbolLibrary library(paths.repository_root);
    BoardSchematicOptions options;
    options.root_name="Zynq_Carrier";options.sheet_subdir="schematic";options.reports_dir=scratch/"reports";
    const auto result=build_board_schematic(inputs,library,scratch/"generated",options);
    if(!result.ok())throw std::runtime_error("fresh schematic failed: "+result.report);
    return result.root_path;
}
}
