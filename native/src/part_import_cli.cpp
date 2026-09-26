#include "schgen/part_import.hpp"
#include <iostream>
#include <set>

namespace schgen {
std::optional<int> run_part_import_command(int argc,char** argv){
    if(argc<2||std::string(argv[1])!="part-import")return std::nullopt;
    PartImportRequest request;
    std::filesystem::path catalog;
    bool overwrite=false;
    std::set<std::string> seen;
    for(int i=2;i<argc;++i){
        const std::string option=argv[i];
        if(!seen.insert(option).second)throw PartImportError("duplicate option "+option);
        if(option=="--overwrite"){overwrite=true;continue;}
        if(option!="--lcsc"&&option!="--name"&&option!="--parts-root"&&option!="--from-json"&&option!="--catalog")
            throw PartImportError("unknown part-import option "+option);
        if(++i==argc||std::string(argv[i]).empty())throw PartImportError("missing value for "+option);
        const std::string value=argv[i];
        if(option=="--lcsc")request.lcsc=value;
        else if(option=="--name")request.name=value;
        else if(option=="--parts-root")request.parts_root=value;
        else if(option=="--from-json")request.from_json=value;
        else catalog=value;
    }
    if(request.parts_root.empty())throw PartImportError("part-import requires --parts-root DIRECTORY");
    if(!request.from_json&&request.lcsc.empty())throw PartImportError("part-import requires --from-json FILE or --lcsc ID");
    const auto plan=prepare_part_import_request(request,request.from_json?PartTransport{}:part_curl_transport());
    const auto published=publish_part_import(plan,request.parts_root,overwrite);
    for(const auto& diagnostic:plan.diagnostics)std::cerr<<diagnostic<<'\n';
    if(!catalog.empty()&&!compile_imported_part_catalog(request.parts_root,catalog))
        throw PartImportError("part files published but catalog refresh failed: "+catalog.string());
    std::cout<<"Imported "<<plan.part.safe_name<<": "<<plan.pad_count<<" pads, "
             <<plan.files.size()<<" files at "<<published.string()<<'\n';
    return 0;
}
} // namespace schgen
