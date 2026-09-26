#include "schgen/authoring_purity_config.hpp"
#include "schgen/authoring_context.hpp"
#include "schgen/json.hpp"
#include <cctype>
#include <map>
#include <set>
#include <stdexcept>

namespace schgen {
namespace {
namespace fs = std::filesystem;
bool starts(const std::string& text, const std::string& prefix) { return text.compare(0,prefix.size(),prefix)==0; }
fs::path resolve(const fs::path& directory, const std::string& text) {
    if (text.empty() || text.find('\0')!=text.npos) throw std::runtime_error("empty/NUL evidence path");
    const fs::path path(text);
    return fs::weakly_canonical(path.is_absolute()?path:directory/path);
}
std::vector<std::string> strings(const JsonNode& node, const std::string& where) {
    if (node.kind!=JsonKind::Array) throw std::runtime_error(where+": expected array");
    std::vector<std::string> result;
    for (const auto& value:node.array_value) {
        if (value.kind!=JsonKind::String || value.string_value.empty() || value.string_value.find('\0')!=std::string::npos)
            throw std::runtime_error(where+": expected nonempty NUL-free strings");
        result.push_back(value.string_value);
    }
    return result;
}
std::vector<std::string> tokenize(const std::string& command) {
    std::vector<std::string> words;
    std::string word;
    char quote=0; bool escaped=false, present=false;
    for (char ch:command) {
        if (ch=='\0' || ch=='\n' || ch=='\r' || ch=='`' || ch=='$')
            throw std::runtime_error("compile command contains shell expansion/control characters");
        if (escaped) { word+=ch; escaped=false; present=true; continue; }
        if (ch=='\\' && quote!='\'') { escaped=true; present=true; continue; }
        if (quote) { if (ch==quote) quote=0; else word+=ch; present=true; continue; }
        if (ch=='\'' || ch=='"') { quote=ch; present=true; continue; }
        if (std::isspace(static_cast<unsigned char>(ch))) {
            if (present) { words.push_back(word); word.clear(); present=false; }
            continue;
        }
        if (std::string(";|&><()").find(ch)!=std::string::npos)
            throw std::runtime_error("compile command contains a shell operator");
        word+=ch; present=true;
    }
    if (quote || escaped) throw std::runtime_error("unterminated compile command quote/escape");
    if (present) words.push_back(word);
    return words;
}
std::vector<std::string> frontend(const std::vector<std::string>& args, const fs::path& directory,
    const fs::path& source, const fs::path& compiler, const fs::path& output) {
    if (args.empty() || resolve(directory,args.front())!=compiler)
        throw std::runtime_error("compile command driver differs from configured compiler");
    std::vector<std::string> result;
    unsigned source_count=0,output_count=0;
    for (std::size_t i=1;i<args.size();++i) {
        const auto& arg=args[i];
        const auto next=[&]() -> const std::string& {
            if (++i==args.size()) throw std::runtime_error("missing compile argument after "+arg);
            return args[i];
        };
        if (arg=="-c" || arg=="-MD" || arg=="-MMD" || arg=="-MP" || arg=="-g" || arg=="-g0" || arg=="-g1" || arg=="-g2" || arg=="-g3") continue;
        if (arg=="-o") {
            if (resolve(directory,next())!=output) throw std::runtime_error("compile argv -o differs from its target-authority output");
            ++output_count; continue;
        }
        if (arg=="-MF" || arg=="-MT" || arg=="-MQ") { (void)next(); continue; }
        if ((starts(arg,"-W") && !starts(arg,"-Wp,") && !starts(arg,"-Wl,") && !starts(arg,"-Wa,")) || arg=="-pedantic" || arg=="-pedantic-errors") continue;
        if (arg=="-std=c++17" || arg=="-ffp-contract=off") continue;
        if (arg=="-I" || arg=="-isystem" || arg=="-iquote") {
            // Preserve compiler search precedence. The semantic checker also
            // requires the physical path to be in configured trust roots.
            result.push_back(arg); result.push_back(resolve(directory,next()).string()); continue;
        }
        if (starts(arg,"-I") && arg.size()>2) { result.push_back("-I"+resolve(directory,arg.substr(2)).string()); continue; }
        if (starts(arg,"-isystem") && arg.size()>8) { result.push_back("-isystem"); result.push_back(resolve(directory,arg.substr(8)).string()); continue; }
        if (arg=="-isysroot" || arg=="-resource-dir") { result.push_back(arg); result.push_back(resolve(directory,next()).string()); continue; }
        if (arg=="-D" || arg=="-U" || arg=="-target") { result.push_back(arg); result.push_back(next()); continue; }
        if (arg=="-arch") { if (next()!="arm64") throw std::runtime_error("unsupported compile architecture"); result.push_back("-target"); result.push_back("arm64-apple-macos"); continue; }
        if ((starts(arg,"-D") || starts(arg,"-U")) && arg.size()>2) { result.push_back(arg); continue; }
        if (starts(arg,"-stdlib=") || starts(arg,"-mmacosx-version-min=") || starts(arg,"-march=") || starts(arg,"-mcpu=") ||
            arg=="-O0" || arg=="-O1" || arg=="-O2" || arg=="-O3" || arg=="-Os" || arg=="-Oz" || arg=="-Og" ||
            arg=="-pthread" || arg=="-fPIC" || arg=="-fpic" || arg=="-fPIE" || arg=="-fpie") { result.push_back(arg); continue; }
        if (!arg.empty() && arg.front()!='-' && arg.front()!='@' && resolve(directory,arg)==source) { ++source_count; continue; }
        throw std::runtime_error("unsupported/opaque compile argument: "+arg);
    }
    if (source_count!=1) throw std::runtime_error("compile command must contain its one declared source");
    if (output_count!=1) throw std::runtime_error("compile command must contain its one declared object output");
    return result;
}
std::string cmake_target(const std::string& output) {
    // CMake's emitted object ownership, not argv order or a source filename
    // heuristic. Production target names are explicit trusted configuration.
    std::string result;
    bool after_files=false;
    for (const auto& item:fs::path(output)) {
        const auto component=item.string();
        if (after_files && component.size()>4 && component.substr(component.size()-4)==".dir") {
            if (!result.empty()) throw std::runtime_error("ambiguous CMake object target: "+output);
            result=component.substr(0,component.size()-4);
        }
        after_files=component=="CMakeFiles";
    }
    return result;
}
AuthoringPurityResult configured_check(const fs::path& repository,const fs::path& configuration,bool census) {
    try {
        const auto config=load_authoring_purity_configuration(repository,configuration);
        const auto scope=native_authoring_purity_scope();
        return census?check_authoring_purity(repository,scope,config.commands,config.toolchain):
                      check_authoring_purity_closure(repository,scope,config.commands,config.toolchain);
    } catch (const std::exception& error) {
        AuthoringPurityResult result;
        result.findings.push_back({"incomplete-evidence",configuration.string(),{},error.what(),0,0});
        return result;
    }
}
} // namespace
AuthoringPurityConfiguration load_authoring_purity_configuration(const fs::path& repository,const fs::path& configuration) {
    const auto root=fs::canonical(repository), file=fs::canonical(configuration);
    const auto config=parse_json_file(file.string());
    reject_unknown_keys(config,{"schema","compiler","libclang","compile_commands","system_include_directories","production_targets"},"authoring purity configuration");
    if (require_string(config,"schema",false,"purity")!="schgen.authoring-purity.toolchain.v1")
        throw std::runtime_error("unsupported authoring purity configuration schema");
    const auto path=[&](const std::string& field) { return fs::canonical(resolve(file.parent_path(),require_string(config,field,false,"purity"))); };
    const auto compiler=path("compiler");
    if (!fs::is_regular_file(compiler)) throw std::runtime_error("configured compiler is not a regular file");
    AuthoringPurityConfiguration result;
    const auto* target_values=object_field(config,"production_targets");
    if (!target_values) throw std::runtime_error("missing production_targets source authority");
    const auto targets=strings(*target_values,"production_targets");
    const std::set<std::string> selected(targets.begin(),targets.end());
    if (selected.empty() || selected.size()!=targets.size()) throw std::runtime_error("empty/duplicate production target authority");
    for (const auto& target:selected)
        if (target=="." || target==".." || target.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")!=std::string::npos)
            throw std::runtime_error("invalid production target name "+target);
    std::set<std::string> observed_targets;
    result.toolchain.libclang=path("libclang").string();
    const auto* includes=object_field(config,"system_include_directories");
    if (!includes) throw std::runtime_error("missing system_include_directories");
    for (const auto& include:strings(*includes,"system_include_directories")) {
        const auto directory=fs::canonical(resolve(file.parent_path(),include));
        if (!fs::is_directory(directory)) throw std::runtime_error("system include is not a directory");
        const auto relative=directory.lexically_relative(root).generic_string();
        if (!starts(relative,"../") && relative!="..") throw std::runtime_error("project directory cannot be a trusted system include");
        result.toolchain.system_include_directories.push_back(directory.string());
    }
    if (result.toolchain.system_include_directories.empty()) throw std::runtime_error("empty system include trust roots");
    const auto database=path("compile_commands");
    const auto commands=parse_json_file(database.string());
    if (commands.kind!=JsonKind::Array || commands.array_value.empty()) throw std::runtime_error("empty/invalid compilation database");
    std::map<std::string,std::vector<std::string>> unique;
    for (const auto& command:commands.array_value) {
        reject_unknown_keys(command,{"directory","file","arguments","command","output"},"compile command");
        const auto output_text=require_string(command,"output",false,"compile command");
        const auto target=cmake_target(output_text);
        if (!selected.count(target)) continue; // Unrelated tests/instrumentation are not production evidence.
        observed_targets.insert(target);
        const auto directory=fs::canonical(resolve(database.parent_path(),require_string(command,"directory",false,"compile command")));
        const auto source=fs::canonical(resolve(directory,require_string(command,"file",false,"compile command")));
        const auto relative=source.lexically_relative(root).generic_string();
        if (relative.empty() || relative==".." || starts(relative,"../")) continue; // Build dependencies are not repository sources.
        const auto extension=source.extension().string();
        if (extension!=".cpp" && extension!=".cc" && extension!=".cxx" && extension!=".C") continue;
        const auto* argv=object_field(command,"arguments");
        const auto* text=object_field(command,"command");
        if ((argv!=nullptr)==(text!=nullptr)) throw std::runtime_error("compile command needs exactly one of arguments/command");
        const auto args=argv?strings(*argv,"compile arguments"):tokenize(require_string(command,"command",false,"compile command"));
        auto normalized=frontend(args,directory,source,compiler,resolve(directory,output_text));
        const auto previous=unique.emplace(relative,normalized);
        if (!previous.second && previous.first->second!=normalized) throw std::runtime_error("ambiguous compiler configurations for "+relative);
    }
    for (const auto& target:selected) if (!observed_targets.count(target)) throw std::runtime_error("production target absent from compile database: "+target);
    for (auto& [source,args]:unique) result.commands.push_back({source,std::move(args)});
    if (result.commands.empty()) throw std::runtime_error("compilation database has no repository C++ sources");
    return result;
}
AuthoringPurityResult check_native_authoring_purity(const fs::path& repository,const fs::path& config,const AuthoringContext& context) {
    // Inspect the actual callbacks that the board caller will pass unchanged
    // into construction. Never execute an unknown callback to identify it.
    try { require_native_authoring_context(context); }
    catch (const std::exception& error) {
        AuthoringPurityResult result;
        result.findings.push_back({"unverified-context",{}, {},error.what(),0,0});
        return result;
    }
    auto result=configured_check(repository,config,false);
    result.native_context_verified=true;
    return result;
}
AuthoringPurityResult check_native_authoring_purity_census(const fs::path& repository,const fs::path& config) { return configured_check(repository,config,true); }
} // namespace schgen
