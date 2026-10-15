#include "../src/floorplan_internal.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <locale>
#include <regex>

namespace {
struct LocaleRestore {
    std::locale previous=std::locale();
    ~LocaleRestore(){std::locale::global(previous);}
};
struct AtIsWord : std::ctype<char> {
    static const mask* classification(){
        static const auto table=[] {
            std::array<mask,table_size> values{};
            std::copy_n(classic_table(),table_size,values.begin());
            values[static_cast<unsigned char>('@')]|=alnum;
            return values;
        }();
        return table.data();
    }
    AtIsWord():std::ctype<char>(classification()){}
};
}
int main(){try{
    LocaleRestore restore;std::size_t checks=0;
    for(const auto& locale:{std::locale::classic(),std::locale(std::locale::classic(),new AtIsWord)}){
        std::locale::global(locale);
        const std::regex reference(R"(\b(rj45|usb_uart)_connector\b)");
        const auto check=[&](const std::string& text){
            std::set<std::string> expected;
            for(auto m=std::sregex_iterator(text.begin(),text.end(),reference);m!=std::sregex_iterator();++m)
                expected.insert(m->str());
            if(schgen::floorplan_detail::deferred_connector_names(text)!=expected)
                throw std::runtime_error("literal connector recognition differs from independent regex oracle at case "+std::to_string(checks));
            ++checks;
        };
        for(const auto* text:{"","rj45_connector","usb_uart_connector","rj45_connector usb_uart_connector rj45_connector",
                "notrj45_connector usb_uart_connectors","rj45_connector_usb_uart_connector","RJ45_connector",
                "rj45_connectorrj45_connector rj45_connector","usb_uart_connectorusb_uart_connector usb_uart_connector",
                "(rj45_connector),[usb_uart_connector]","@rj45_connector@ @usb_uart_connector@"})check(text);
        for(const std::string token:{"rj45_connector","usb_uart_connector"})
            for(unsigned left=0;left<256;++left)for(unsigned right=0;right<256;++right){
                // All byte pairs include NULs, non-ASCII bytes, punctuation,
                // and identifier characters on either side of each literal.
                check(std::string(1,static_cast<char>(left))+token+static_cast<char>(right));
            }
    }
    std::cout<<checks<<" deferred connector recognition contracts PASS\n";
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
