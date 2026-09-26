#include "schgen/project_authoring.hpp"
#include <iostream>
#include <stdexcept>

int main() {
    try {
        std::size_t checks=0,locals=0;
        const auto require=[&](bool ok,const char* why) { ++checks; if (!ok) throw std::runtime_error(why); };
        const auto rejected=[&](const schgen::ProjectSubsystemDefinition& definition) {
            bool failed=false;
            try { (void)schgen::author_registered_project_definition(definition,schgen::SubsystemMeta{},{}); }
            catch (const schgen::CircuitAuthoringError&) { failed=true; }
            require(failed,"altered project callable identity was accepted");
        };
        const schgen::ProjectSubsystemDefinition* previous=nullptr;
        for (const auto& original:schgen::project_subsystem_definitions()) {
            if (!original.circuit) continue;
            ++locals;
            auto edited=original;
            bool invoked=false;
            edited.circuit=[&](const schgen::SubsystemMeta&,const schgen::AuthoringContext&) {
                invoked=true; return schgen::CircuitSheetIr{};
            };
            rejected(edited); require(!invoked,"unknown callback executed during target checking");
            edited=original; edited.project="unregistered-project"; rejected(edited);
            edited=original; edited.name="unregistered-name"; rejected(edited);
            edited=original; edited.adapter=true; rejected(edited);
            edited=original; edited.connector_ref="J1"; rejected(edited);
            edited=original; edited.circuit={}; rejected(edited);
            if (previous) { edited=original; edited.circuit=previous->circuit; rejected(edited); }
            previous=&original;
        }
        require(locals==22,"explicit project local target coverage changed");
        std::cout<<"authoring checked dispatch: "<<checks<<" contracts PASS\n";
    } catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
