#include "schgen/assembly_documents.hpp"
#include "schgen/manufacturing_checks.hpp"
#include "schgen/atomic_file.hpp"
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <zlib.h>

using namespace schgen;
namespace fs=std::filesystem;
namespace {
std::size_t assertions=0;
void require(bool p,const std::string& why){++assertions;if(!p)throw std::runtime_error(why);}
std::string read(const fs::path& p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("cannot read "+p.string());return {std::istreambuf_iterator<char>(f),{}};}
void write(const fs::path& p,const std::string& s){write_atomic_file(p.string(),{s.begin(),s.end()});}
const JsonNode& field(const JsonNode& n,const std::string& key){auto p=object_field(n,key);if(!p)throw std::runtime_error("missing fixture field "+key);return *p;}
std::string str(const JsonNode& n,const std::string& key){return field(n,key).string_value;}
double num(const JsonNode& n,const std::string& key){return field(n,key).number_value;}
std::vector<std::string> strings(const JsonNode& n){std::vector<std::string> o;for(const auto& v:n.array_value)o.push_back(v.string_value);return o;}
void exact(const std::string& got,const fs::path& file,const fs::path& output){auto want=read(file);write(output,got);if(got!=want){std::size_t i=0;while(i<std::min(got.size(),want.size())&&got[i]==want[i])++i;throw std::runtime_error(file.string()+": bytes differ at "+std::to_string(i)+" actual saved in "+output.string());}++assertions;}
template<class F>void throws(F f,const std::string& text){bool caught=false;try{f();}catch(const std::exception& e){caught=true;require(std::string(e.what()).find(text)!=std::string::npos,"unexpected error: "+std::string(e.what()));}require(caught,"expected error containing "+text);}
PcbFootprintPool pool(const JsonNode& n){PcbFootprintPool p;for(const auto& [k,v]:n.object_value)p[k]=pcb_check_footprint(k,v.string_value);return p;}
PcbEmitPolicy policy(const JsonNode& n){auto p=default_pcb_emit_policy();for(const auto& [k,v]:field(n,"header_descriptions").object_value)p.header_descriptions.emplace_back(k,v.string_value);for(const auto& [k,v]:field(n,"switch_descriptions").object_value)p.switch_descriptions.emplace_back(k,v.string_value);return p;}
Stm32PinMap stm32(const JsonNode& n){Stm32PinMap out;out.value=str(n,"value");for(const auto& [k,v]:field(n,"nets").object_value)out.nets[k]={str(v,"net"),str(v,"port"),static_cast<int>(num(v,"pin")),strings(field(v,"j_pins"))};return out;}
void groups(const PcbModel& m,const AssemblyPlan& p,const JsonNode& expected){
    for(const auto& [kind,phases]:std::vector<std::pair<std::string,bool>>{{"steps",false},{"phases",true}}){const auto& want=field(expected,kind).array_value;require((phases?p.phases.size():p.steps.size())==want.size(),kind+" count");
        for(std::size_t i=0;i<want.size();++i){const auto& row=want[i];const auto ids=phases?p.phases[i].insts:p.steps[i].insts;
            require((phases?p.phases[i].slug:p.steps[i].slug)==str(row,"slug"),kind+" slug");require((phases?p.phases[i].title:p.steps[i].title)==str(row,"title"),kind+" title");require((phases?p.phases[i].n:p.steps[i].n)==num(row,"n"),kind+" ordinal");
            require(ids.size()==field(row,"insts").array_value.size(),kind+" member count");for(std::size_t j=0;j<ids.size();++j)require(ids[j]==field(row,"insts").array_value[j].number_value,kind+" order: "+m.insts.at(ids[j]).ref);
            if(phases){require(p.phases[i].sheets==strings(field(row,"sheets")),"phase sheets");require(p.phases[i].checkpoints==strings(field(row,"checkpoints")),"phase checkpoints");require(p.phases[i].lead==str(row,"lead"),"phase lead");}else require(p.steps[i].notes==strings(field(row,"notes")),"step notes");
        }
    }
}
uint32_t be32(const std::string& s,std::size_t off){uint32_t n=0;for(int i=0;i<4;++i)n=(n<<8)|static_cast<unsigned char>(s.at(off+i));return n;}
std::string rgb(const std::string& png,int width,int height){
    require(png.substr(0,8)==std::string("\x89PNG\r\n\x1a\n",8),"PNG signature");require(be32(png,16)==static_cast<unsigned>(width)&&be32(png,20)==static_cast<unsigned>(height),"PNG dimensions");
    std::string compressed;for(std::size_t p=8;p<png.size();){auto n=be32(png,p);if(png.substr(p+4,4)=="IDAT")compressed+=png.substr(p+8,n);p+=n+12;}
    const int stride=width*3;std::string filtered(static_cast<std::size_t>(stride+1)*height,'\0');uLongf size=filtered.size();require(uncompress(reinterpret_cast<Bytef*>(filtered.data()),&size,reinterpret_cast<const Bytef*>(compressed.data()),compressed.size())==Z_OK&&size==filtered.size(),"PNG deflate");
    std::string out(static_cast<std::size_t>(stride)*height,'\0');for(int y=0;y<height;++y){auto f=static_cast<unsigned char>(filtered[static_cast<std::size_t>(y)*(stride+1)]);require(f<=4,"PNG filter");for(int x=0;x<stride;++x){auto pos=static_cast<std::size_t>(y)*stride+x;int a=x>=3?static_cast<unsigned char>(out[pos-3]):0,b=y?static_cast<unsigned char>(out[pos-stride]):0,c=x>=3&&y?static_cast<unsigned char>(out[pos-stride-3]):0;int p=a+b-c,pa=std::abs(p-a),pb=std::abs(p-b),pc=std::abs(p-c);int predictor=f==1?a:f==2?b:f==3?(a+b)/2:f==4?(pa<=pb&&pa<=pc?a:pb<=pc?b:c):0;out[pos]=static_cast<char>(static_cast<unsigned char>(filtered[static_cast<std::size_t>(y)*(stride+1)+x+1])+predictor);}}
    return out;
}
void check_images(const std::vector<AssemblyImage>& images,const std::vector<JsonNode>& expected,const fs::path& output,const std::string& name){
    require(images.size()==expected.size(),"assembly image inventory");
    for(std::size_t n=0;n<images.size();++n){const auto& i=images[n];const auto& e=expected[n];require(i.filename==str(e,"filename"),"PNG filename");write(output/i.filename,i.png);const auto pixels=rgb(i.png,static_cast<int>(num(e,"width")),static_cast<int>(num(e,"height")));require(pcb_sha256(pixels)==str(e,"rgb_sha256"),name+" "+i.filename+": RGB parity failed");require(pcb_sha256(i.png)==str(e,"png_sha256"),name+" "+i.filename+": PNG byte parity failed");}
}
void project(const fs::path& root,const fs::path& scratch,const std::string& name){
    const auto fixture=root/"native/tests/data/manufacturing"/name;const auto output=scratch/name;const auto input=parse_json_file((fixture/"inputs.json").string());
    const auto raw=parse_json_file((root/"native/tests/data/pcb_emit"/(name+".json")).string());auto m=pcb_model_from_json(field(raw,"model"),pool(field(raw,"footprints")));auto pol=policy(raw);auto power=power_result_from_json(field(input,"power"));auto plan=assembly_plan(m,power,pol);
    groups(m,plan,parse_json_file((fixture/"plan.json").string()));exact(render_assembly_markdown(m,plan,name),fixture/"ASSEMBLY.md",output/"ASSEMBLY.md");
    std::cout<<name<<": plan and assembly Markdown exact\n";
    auto paths=resolve_project_paths(root,name);auto sheets=load_project_circuits(paths);
    auto si=load_si_constraints(sheets,paths.project_root/"research/si_spec.json");auto verdict=check_si_constraints(si);require(verdict.ok,"live SI verdict failed: "+verdict.summary());
    exact(render_si_design_rules(si,"(version 1)\n# preserve caller rule\n"),fixture/"si.kicad_dru",output/"si.kicad_dru");exact(render_si_markdown(si),fixture/"SI_CONSTRAINTS.md",output/"SI_CONSTRAINTS.md");
    require(verdict.summary()+"\n"==read(fixture/"si_summary.txt"),"SI exact summary");
    const auto run_path=output/"si-run";write(run_path/"rules.kicad_dru","(version 1)\n# preserve caller rule\n");const auto run=run_si_constraints(sheets,paths.project_root/"research/si_spec.json",run_path/"rules.kicad_dru",run_path/"SI.md");require(run.verdict.ok,"SI run checks real model");require(read(run.md)==render_si_markdown(si)&&read(run.dru)==render_si_design_rules(si,"(version 1)\n# preserve caller rule\n"),"SI run publishes rules and Markdown");throws([&]{run_si_constraints(sheets,paths.project_root/"research/si_spec.json",run.md,run.md);},"distinct");
    auto in=prepare_manufacturing_manifest(sheets,stm32(field(input,"stm32")),ManufacturingXdc{5,{35,34,35},std::nullopt},"xc7z020clg400-1",{12.34565,7});
    for(const auto& a:field(input,"artifacts").array_value)in.artifacts.push_back({str(a,"path"),str(a,"sha256")});
    exact(render_manufacturing_manifest(in),fixture/"manifest.json",output/"manifest.json");
    std::cout<<name<<": SI and live-analysis manifest exact\n";
    const auto images=render_assembly_images(m,plan);const auto expected=parse_json_file((fixture/"images.json").string()).array_value;check_images(images,expected,output,name);
    std::cout<<name<<": "<<images.size()<<" assembly PNGs exact\n";
}
void mutations(const fs::path& root,const fs::path& scratch){
    const auto raw=parse_json_file((root/"native/tests/data/manufacturing/mutations.json").string());const auto fps=pool(field(raw,"footprints"));
    for(const auto& row:field(raw,"assembly").array_value){auto name=str(row,"name");auto m=pcb_model_from_json(field(row,"model"),fps);auto p=power_result_from_json(field(row,"power"));
        if(auto e=object_field(row,"error")){throws([&]{assembly_plan(m,p);},e->string_value);continue;}
        const auto plan=assembly_plan(m,p);groups(m,plan,field(row,"plan"));require(render_assembly_markdown(m,plan,name)==str(row,"markdown"),name+" mutated assembly Markdown");
        check_images(render_assembly_images(m,plan),field(row,"images").array_value,scratch/"mutations"/name,name);
        if(name=="base"){
            const auto target=scratch/"runs";write(target/"images/stale.png","stale");write(target/"images/keep.txt","keep");
            auto result=run_assembly_documents(m,p,name,target/"ASSEMBLY.md",target/"images");require(field(result,"ok").bool_value,"assembly run result");require(assembly_verdict(result,scratch).first,"assembly successful transport verdict");require(!fs::exists(target/"images/stale.png")&&read(target/"images/keep.txt")=="keep","dedicated image directory cleanup");require(read(target/"ASSEMBLY.md")==str(row,"markdown"),"run writes computed Markdown");
            auto changed=m;changed.insts.front().x+=1;require(render_assembly_images(changed,plan).back().png!=render_assembly_images(m,plan).back().png,"fresh pose affects assembly images");
            auto invalid=plan;invalid.steps.front().insts.push_back(m.insts.size());throws([&]{render_assembly_markdown(m,invalid,name);},"out of range");
            throws([&]{run_assembly_documents(m,p,name,target/"same",target/"same");},"distinct");
            changed=m;changed.insts.front().mod.reset();throws([&]{run_assembly_documents(changed,p,name,target/"ASSEMBLY.md",target/"images");},"unresolved");require(read(target/"ASSEMBLY.md")==str(row,"markdown"),"failed assembly render preserves old Markdown");
            write(target/"blocked","file");throws([&]{run_assembly_documents(m,p,name,target/"blocked/ASSEMBLY.md",target/"images");},"blocked");
        }
    }
    for(const auto& row:field(raw,"si").array_value){std::vector<ProjectCircuit> sheets;for(const auto& s:field(row,"sheets").array_value)sheets.push_back({str(s,"name"),{},decode_intermediate_circuit_ir(field(s,"circuit"))});auto si=build_si_constraints(sheets,parse_signal_specs(field(row,"spec")));const auto v=check_si_constraints(si);
        require(v.ok==field(row,"ok").bool_value&&v.summary()==str(row,"summary"),str(row,"name")+" SI verdict exact");write(scratch/"si-mutants"/(str(row,"name")+"-actual.md"),render_si_markdown(si));write(scratch/"si-mutants"/(str(row,"name")+"-expected.md"),str(row,"markdown"));require(render_si_markdown(si)==str(row,"markdown"),str(row,"name")+" SI Markdown exact");require(render_si_design_rules(si)==str(row,"rules"),str(row,"name")+" SI rules exact");require(render_si_design_rules(si,render_si_design_rules(si))==render_si_design_rules(si),"SI append is idempotent");
        throws([&]{load_si_constraints(sheets,scratch/"absent-si.json");},"not found");
    }
    require(load_si_constraints({},scratch/"absent-si.json").declared.empty(),"no pairs allows missing SI table");
    for(const auto& row:parse_json_file((root/"native/tests/data/manufacturing/fallback.json").string()).array_value){auto path=scratch/"fallback-cases"/(str(row,"name")+".json");if(field(row,"initial").kind!=JsonKind::Null)write(path,str(row,"initial"));ManufacturingCounts counts;for(const auto& [name,n]:field(row,"counts").object_value)counts[name]=static_cast<long long>(n.number_value);auto r=run_manufacturing_fallbacks(counts,path);require(r.ok==field(row,"ok").bool_value&&r.pinned==field(row,"pinned").bool_value&&r.summary()==str(row,"summary"),"fallback exact verdict "+str(row,"name"));require(read(path)==str(row,"final"),"fallback exact baseline bytes "+str(row,"name"));}
    auto pipeline=manufacturing_pipeline_from_json(parse_json_file((root/"native/tests/data/manufacturing/pipeline.json").string()));auto old=render_manufacturing_pipeline(pipeline);pipeline.stages.front().desc="fresh mutation";require(render_manufacturing_pipeline(pipeline)!=old,"pipeline consumes live metadata");auto out=scratch/"runs/pipeline.md";require(run_manufacturing_pipeline(pipeline,out).second,"pipeline first write");const auto stamp=fs::last_write_time(out);require(!run_manufacturing_pipeline(pipeline,out).second&&stamp==fs::last_write_time(out),"pipeline no-change preserves timestamp");pipeline.stages.push_back(pipeline.stages.front());throws([&]{render_manufacturing_pipeline(pipeline);},"duplicate");
    auto baseline=scratch/"runs/fallback.json";auto first=run_manufacturing_fallbacks({{"known",3}},baseline);require(first.ok&&first.pinned,"fallback first-run pin");const auto before=read(baseline);auto failed=run_manufacturing_fallbacks({{"known",3},{"assembly_generation_failed",1}},baseline);require(!failed.ok&&read(baseline)==before&&failed.summary().find("assembly_generation_failed: fired 1 > baseline 0")!=std::string::npos,"fallback zero ceiling enforced without writing");require(run_manufacturing_fallbacks({{"known",1}},baseline).ok&&num(field(parse_json_file(baseline.string()),"counts"),"known")==1,"fallback ceiling decreases");require(!run_manufacturing_fallbacks({{"known",2}},baseline).ok,"fallback ceiling cannot increase");write(baseline,"malformed");require(run_manufacturing_fallbacks({{"known",0}},baseline).pinned,"legacy malformed baseline recovery");
    const auto board=sexpr_loads("(kicad_pcb (segment (width 0.10)) (via (size 0.4) (drill 0.2)) (footprint X (pad \"1\" thru_hole oval (drill oval 0.5 0.3))))");auto demand=measure_manufacturing_board(board,"(constraint track_width (min 0.09mm)) (constraint clearance (min 0.1mm))","{\"min_hole_to_hole\": 0.16, \"min_via_annular_width\":0.001}");require(demand.n_segments==1&&demand.n_vias==1&&demand.n_drills==2&&demand.min_trace_mm==.09&&demand.min_drill_mm==.2&&demand.min_via_annular_mm==.1,"fab actual board + rules extraction");require(check_manufacturing_fab(demand).ok,"fab geometry above floor");demand.min_trace_mm=.09-.0000009;require(check_manufacturing_fab(demand).ok,"fab epsilon accepted");demand.min_trace_mm=.09-.0000011;require(!check_manufacturing_fab(demand).ok,"fab epsilon exceeded");
    auto pcb=scratch/"runs/test.kicad_pcb";write(pcb,sexpr_dumps(board));const auto fab=run_manufacturing_fab(scratch/"runs",pcb,scratch/"absent.dru",scratch/"absent.pro");require(read(scratch/"runs/fab_profile.txt")==fab.report()+"\n","fab run report");throws([&]{run_manufacturing_fab(scratch/"runs",scratch/"absent.pcb",{},{});},"requires an emitted board");
    const auto tree=scratch/"artifact-tree";write(tree/"reports/fixture.txt",std::string("fixture\0\xff\r\n",11));write(tree/"reports/nested/excluded.txt","excluded");write(tree/"manufacturing/not-selected.md","excluded");write(tree/"manifest.json","old");auto artifacts=manufacturing_artifacts(tree,tree/"manifest.json");require(artifacts.size()==1&&artifacts.front().path=="reports/fixture.txt"&&artifacts.front().sha256=="874a5443d83e074f3be349130ec16d1c2bbb1733b2d9205cfbbd46f88f4344cd","artifact selection and binary hash");require(manufacturing_artifacts(tree,tree/"reports/fixture.txt").empty(),"manifest excludes itself");
    ManufacturingManifestInput mi;mi.artifacts={{"stale","stale"}};run_manufacturing_manifest(mi,tree,tree/"manifest.json");auto manifest=parse_json_file((tree/"manifest.json").string());require(field(manifest,"artifacts").array_value.size()==1&&str(field(manifest,"artifacts").array_value[0],"path")=="reports/fixture.txt","manifest run uses live filesystem");write(tree/"reports/fixture.txt","changed");run_manufacturing_manifest(mi,tree,tree/"manifest.json");require(str(field(parse_json_file((tree/"manifest.json").string()),"artifacts").array_value[0],"sha256")==pcb_sha256("changed"),"manifest run rehashes mutated artifacts");
    mi.preflight.extended=std::numeric_limits<long long>::max();require(render_manufacturing_manifest(mi).find("\"extended\": 9223372036854775807")!=std::string::npos,"manifest exact signed 64-bit count");throws([&]{manufacturing_manifest(mi);},"loses precision");mi.preflight.extended=std::numeric_limits<long long>::min();require(render_manufacturing_manifest(mi).find("\"extended\": -9223372036854775808")!=std::string::npos,"manifest negative signed 64-bit count");
    auto xdc=scratch/"runs/test.xdc";write(xdc,"# ignored\r\n# Device: \t mutated-device \r\n# Device: wrong\n");require(manufacturing_xdc_device(xdc)=="mutated-device","XDC device first matching line + whitespace");write(xdc,"# Device: \n# Device: later\n");require(!manufacturing_xdc_device(xdc),"empty first device stops search");
    std::cout<<"frozen assembly/SI mutants and publication/error contracts passed\n";
}
void misc(const fs::path& root,const fs::path& scratch){
    const auto fixtures=root/"native/tests/data/manufacturing";auto pipeline=manufacturing_pipeline_from_json(parse_json_file((fixtures/"pipeline.json").string()));exact(render_manufacturing_pipeline(pipeline),fixtures/"pipeline.md",scratch/"pipeline.md");
    for(const auto& row:parse_json_file((fixtures/"fab.json").string()).array_value){const auto& n=field(row,"demand");ManufacturingBoardDemand d;auto get=[&](const std::string& k)->std::optional<double>{const auto& v=field(n,k);return v.kind==JsonKind::Null?std::nullopt:std::optional<double>(v.number_value);};d.min_trace_mm=get("min_trace_mm");d.min_clearance_mm=get("min_clearance_mm");d.min_drill_mm=get("min_drill_mm");d.min_via_dia_mm=get("min_via_dia_mm");d.min_via_annular_mm=get("min_via_annular_mm");d.min_hole_to_hole_mm=get("min_hole_to_hole_mm");d.pro_via_annular_mm=get("pro_via_annular_mm");d.n_segments=static_cast<std::size_t>(num(n,"n_segments"));d.n_vias=static_cast<std::size_t>(num(n,"n_vias"));d.n_drills=static_cast<std::size_t>(num(n,"n_drills"));const auto r=check_manufacturing_fab(d);require(r.ok==field(row,"ok").bool_value,"fab verdict");require(r.report()==str(row,"report"),"fab exact report: "+str(row,"name"));require(r.errors==strings(field(row,"errors")),"fab errors");}
    require(!assembly_verdict(JsonNode{},root).first,"absent assembly must fail");
    std::cout<<"fabrication and pipeline document exact\n";
}
}
int main(int argc,char** argv){
    try{
        require(argc==3,"usage: manufacturing_contracts REPOSITORY SCRATCH_PARENT");
        const auto root=fs::absolute(argv[1]),parent=fs::absolute(argv[2]);
        fs::create_directories(parent);auto pattern=(parent/"run-XXXXXX").string();
        if(!::mkdtemp(pattern.data()))throw std::runtime_error("cannot create contract scratch directory");
        const fs::path scratch=pattern;fs::current_path(scratch);
        std::cout<<"scratch: "<<scratch<<'\n';
        misc(root,scratch);
        for(const auto& name:{"carrier","devkit_mini"})project(root,scratch,name);
        mutations(root,scratch);
        std::cout<<assertions<<" manufacturing assertions passed\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
