#pragma once
#include <stdexcept>
#include <string>

namespace schgen_test {
// Named, independently prescribed corrections. Substitute only exact
// title/comment bytes in the immutable historical file; retain all other bytes.
inline std::string worksheet_corrected_v1(const std::string& name,std::string original) {
    const auto require=[](bool ok,const char* why){if(!ok)throw std::runtime_error(why);};
    std::string title,continuation;
    if(name=="carrier-board_qwiic") {
        title="QWIIC / STEMMA-QT expansion connector +";continuation="USBLC6 ESD array";
    } else if(name=="carrier-som_j1") {
        title="SoM J1: power / USB / STM32 / JTAG /";continuation="SDIO / ETH MDI";
    } else if(name=="carrier-mechanical") {
        title="Mechanical: M3 mounts + chassis-GND";
        continuation="bond (fiducials are PCB-only, emitted by the placer)";
    } else return original;
    const auto historical=original;
    // Rejoining the prescribed strings must match the complete original title
    // exactly, including spaces; this is not a computed emitter expectation.
    const auto old_line=name=="carrier-mechanical"
        ? "\t\t(title\n\t\t\t\""+title+" "+continuation+"\"\n\t\t)\n"
        : "\t\t(title \""+title+" "+continuation+"\")\n";
    const auto at=original.find(old_line);
    require(at!=std::string::npos && original.find(old_line,at+1)==std::string::npos,
            "named historical title changed");
    require(title.size()<=40 && continuation.size()<=55 && title.size()+1+continuation.size()>40,
            "worksheet correction budgets");
    original.replace(at,old_line.size(),"\t\t(title \""+title+"\")\n");
    const auto close=original.find("\n\t)\n",at);
    require(close!=std::string::npos,"missing title block terminator");
    original.insert(close+1,"\t\t(comment 2 \""+continuation+"\")\n");
    require(original!=historical,"historical overflowing output must not pass as corrected output");
    return original;
}
}
