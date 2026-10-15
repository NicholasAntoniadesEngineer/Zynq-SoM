#pragma once
#include "schgen/native_audit_state.hpp"
#include <cctype>
#include <filesystem>
#include <set>
#include <string>

namespace schgen::audit_detail {
// Clang -M/-MD with our explicit -MT target. Parse its Make escaping, not
// shell quoting; reject variable expansion or malformed/truncated records.
inline std::set<std::filesystem::path> dependency_paths(const std::string& record) {
    const std::string prefix="schgen_audit_deps:";
    if(record.compare(0,prefix.size(),prefix)!=0)
        throw AuditSyntaxError("native audit: invalid compiler dependency target");
    std::set<std::filesystem::path> paths;std::string token;
    const auto finish=[&] {
        if(token.empty())return;
        paths.insert(std::filesystem::absolute(token).lexically_normal());token.clear();
    };
    for(std::size_t i=prefix.size();i<record.size();++i) {
        const char c=record[i];
        if(c=='\\') {
            if(++i==record.size())throw AuditSyntaxError("native audit: truncated dependency escape");
            if(record[i]=='\n'){finish();continue;}
            if(record[i]=='\r'&&i+1<record.size()&&record[i+1]=='\n'){++i;finish();continue;}
            if(record[i]!=' '&&record[i]!='\t'&&record[i]!='#')
                throw AuditSyntaxError("native audit: unsupported dependency escape");
            token+=record[i];
        } else if(c=='$') {
            if(i+1==record.size()||record[++i]!='$')throw AuditSyntaxError("native audit: dependency variable expansion");
            token+='$';
        } else if(std::isspace(static_cast<unsigned char>(c)))finish();
        else if(c=='#'||c=='\0')throw AuditSyntaxError("native audit: malformed dependency token");
        else token+=c;
    }
    finish();
    if(paths.empty())throw AuditSyntaxError("native audit: empty compiler dependencies");
    return paths;
}
}
