// Bootstrap/CLI smoke checks are native executables, not Python/shell programs.
#include "schgen/process.hpp"
#include <array>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <unistd.h>

namespace fs=std::filesystem;
namespace {
void require(bool condition,const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}
std::string read(const fs::path& path) {
    std::ifstream stream(path,std::ios::binary);
    require(bool(stream),"cannot read "+path.string());
    const std::string bytes{std::istreambuf_iterator<char>(stream),{}};
    require(!stream.bad(),"failed reading "+path.string()); return bytes;
}
bool native_magic(const std::string& bytes) {
    if (bytes.size()<4) return false;
    const std::array<unsigned char,4> magic{
        static_cast<unsigned char>(bytes[0]),static_cast<unsigned char>(bytes[1]),
        static_cast<unsigned char>(bytes[2]),static_cast<unsigned char>(bytes[3])};
    // ELF and both byte orders of 32/64-bit Mach-O/universal Mach-O.
    for (const auto& allowed:std::array<std::array<unsigned char,4>,7>{{
        {{0x7f,'E','L','F'}},{{0xfe,0xed,0xfa,0xce}},{{0xce,0xfa,0xed,0xfe}},
        {{0xfe,0xed,0xfa,0xcf}},{{0xcf,0xfa,0xed,0xfe}},
        {{0xca,0xfe,0xba,0xbe}},{{0xca,0xfe,0xba,0xbf}}}})
        if (magic==allowed) return true;
    return false;
}
void check_cache(const std::string& bytes) {
    std::map<std::string,std::string> values; std::istringstream lines(bytes);
    std::string line;
    while (std::getline(lines,line)) {
        if (!line.empty()&&line.back()=='\r') line.pop_back();
        if (line.empty()||line.front()=='#'||line.rfind("//",0)==0) continue;
        const auto colon=line.find(':'),equal=line.find('=');
        if (colon==line.npos||equal==line.npos||colon>equal) continue;
        const auto key=line.substr(0,colon),value=line.substr(equal+1);
        require(values.emplace(key,value).second,"duplicate CMake cache entry: "+key);
        for (const std::string prefix:{"Python_","Python3_","PYTHON_","_Python","nanobind","NANOBIND"})
            require(key.rfind(prefix,0)!=0,"Python/nanobind discovery present in native CI cache: "+key);
    }
    require(values.count("SCHGEN_BUILD_PYTHON")&&values.at("SCHGEN_BUILD_PYTHON")=="OFF",
            "native CI requires explicit SCHGEN_BUILD_PYTHON=OFF");
    require(values.count("BUILD_TESTING")&&values.at("BUILD_TESTING")=="ON",
            "native CI requires BUILD_TESTING=ON");
}
struct Scratch {
    fs::path path;
    Scratch() {
        auto pattern=(fs::temp_directory_path()/"schgen-ci-smoke-XXXXXX").string();
        require(::mkdtemp(pattern.data())!=nullptr,"cannot create private CI smoke directory"); path=pattern;
    }
    ~Scratch() { std::error_code error; fs::remove_all(path,error); }
};
std::string success(const std::vector<std::string>& args) {
    const auto result=schgen::run_process(args,std::chrono::minutes(2));
    require(result.exit_code==0,"native smoke command failed: "+args.front()+"\n"+result.stdout_text+result.stderr_text);
    return result.stdout_text;
}
void check_cli(const fs::path& executable,const fs::path& repo) {
    require(native_magic(read(executable)),"schgen must be a native Mach-O/ELF executable, not a script");
    require(success({executable.string(),"self-check"}).find("self-check ok")!=std::string::npos,
            "CLI self-check did not report actual kernel checks");
    require(success({executable.string(),"--help"}).find("catalog-compile")!=std::string::npos,
            "CLI command surface missing catalog compiler");
    const auto missing=schgen::run_process({executable.string(),"catalog-compile"});
    require(missing.exit_code!=0&&missing.stderr_text.find("usage:")!=std::string::npos,
            "invalid catalog invocation must fail with its diagnostic");
    Scratch scratch;
    for (const auto& kind:{std::string("catalog"),std::string("circuit")}) {
        const auto source=kind=="catalog"?repo/"parts":repo/"carrier/subsystems";
        const auto a=scratch.path/(kind+"-a.bin"),b=scratch.path/(kind+"-b.bin");
        success({executable.string(),kind+"-compile",source.string(),a.string()});
        success({executable.string(),kind+"-compile",source.string(),b.string()});
        require(!read(a).empty()&&read(a)==read(b),kind+" compilation is empty or nondeterministic");
    }
}
void check_environment(const fs::path& cli,const std::string& version,
                       const fs::path& footprints,const fs::path& symbols,const fs::path& models) {
    auto actual=success({cli.string(),"version"});
    while (!actual.empty()&&(actual.back()=='\n'||actual.back()=='\r')) actual.pop_back();
    require(actual==version,"KiCad version mismatch: expected "+version+", observed "+actual);
    for (const auto& path:{footprints/"Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod",
                          symbols/"Device.kicad_sym",
                          models/"Resistor_SMD.3dshapes/R_0603_1608Metric.step"})
        require(fs::is_regular_file(path)&&fs::file_size(path)>0,"required installed KiCad library asset missing: "+path.string());
    std::cout<<"KiCad "<<actual<<" and native library prerequisites present\n";
}
void contracts(const fs::path& self) {
    const std::string good="// native-only\nSCHGEN_BUILD_PYTHON:BOOL=OFF\nBUILD_TESTING:BOOL=ON\n";
    check_cache(good);
    std::size_t rejected=0;
    for (const auto& bad:{std::string{},std::string("SCHGEN_BUILD_PYTHON:BOOL=ON\nBUILD_TESTING:BOOL=ON\n"),
        std::string("SCHGEN_BUILD_PYTHON:BOOL=OFF\nBUILD_TESTING:BOOL=OFF\n"),
        good+"Python_EXECUTABLE:FILEPATH=/python\n",good+"nanobind_DIR:PATH=/nanobind\n",
        good+"SCHGEN_BUILD_PYTHON:BOOL=OFF\n"}) {
        try { check_cache(bad); } catch (const std::runtime_error&) { ++rejected; }
    }
    require(rejected==6,"cache mutation checks failed to reject a poisoned configuration");
    require(!native_magic("#!/usr/bin/python3\n")&&!native_magic(""),"script/truncated executable accepted");
    require(native_magic(read(self)),"current smoke executable is not native");
    std::cout<<"10 native bootstrap contracts passed\n";
}
void bootstrap_contracts(const std::string& cmake,const std::string& script) {
    Scratch scratch;
    const auto archive=scratch.path/"bad.tar.gz",work=scratch.path/"work",prefix=scratch.path/"prefix";
    { std::ofstream stream(archive); stream<<"not the pinned upstream source archive"; require(bool(stream),"write negative archive fixture"); }
    std::vector<std::string> args{cmake,"-DSCHGEN_ZLIB_ARCHIVE="+archive.string(),
        "-DSCHGEN_DEPENDENCY_WORK="+work.string(),"-DSCHGEN_DEPENDENCY_PREFIX="+prefix.string(),"-P",script};
    const auto hash=schgen::run_process(args);
    require(hash.exit_code!=0&&hash.stderr_text.find("checksum mismatch")!=std::string::npos,"bootstrap accepted an unverified archive");
    require(!fs::exists(work)&&!fs::exists(prefix),"hash rejection must precede all output writes");
    args[1]="-DSCHGEN_ZLIB_ARCHIVE=relative.tar.gz";
    const auto relative=schgen::run_process(args);
    require(relative.exit_code!=0&&relative.stderr_text.find("explicit absolute path")!=std::string::npos,"bootstrap accepted an ambiguous archive path");
    args[1]="-DSCHGEN_ZLIB_ARCHIVE="+(scratch.path/"missing.tar.gz").string();
    const auto missing=schgen::run_process(args);
    require(missing.exit_code!=0&&missing.stderr_text.find("not found")!=std::string::npos,"bootstrap accepted absent source");
    require(!fs::exists(work)&&!fs::exists(prefix),"invalid source must not create outputs");
    std::cout<<"5 native offline-bootstrap rejection contracts passed\n";
}
}
int main(int argc,char** argv) {
    try {
        if (argc==2&&std::string(argv[1])=="--contracts") contracts(fs::canonical(argv[0]));
        else if (argc==4&&std::string(argv[1])=="--bootstrap-contracts") bootstrap_contracts(argv[2],argv[3]);
        else if (argc==3&&std::string(argv[1])=="--cache") check_cache(read(argv[2]));
        else if (argc==4&&std::string(argv[1])=="--cli") check_cli(fs::canonical(argv[2]),fs::canonical(argv[3]));
        else if (argc==7&&std::string(argv[1])=="--environment") check_environment(argv[2],argv[3],argv[4],argv[5],argv[6]);
        else throw std::runtime_error("usage: schgen_ci_smoke --contracts | --cache CACHE | --cli SCHGEN REPO | --environment KICAD VERSION FOOTPRINTS SYMBOLS MODELS");
        std::cout<<"Native CI smoke PASS\n";
    } catch (const std::exception& e) { std::cerr<<"Native CI smoke FAIL: "<<e.what()<<'\n'; return 1; }
}
