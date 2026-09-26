#include "part_import_internal.hpp"
#include "schgen/atomic_file.hpp"
#include "schgen/model3d.hpp"
#include <array>
#include <fstream>
#include <set>
#include <zlib.h>

namespace schgen {
namespace {
using namespace part_import_detail;
const std::string agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
void validate_url_token(const std::string& s) {
    if(s.empty() || !std::all_of(s.begin(),s.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='-'||c=='_';}))
        throw PartImportError("invalid EasyEDA URL identifier: "+s);
}
std::string utf8_replace(const std::string& s) {
    std::string out;
    for(std::size_t i=0;i<s.size();) {
        const auto c=static_cast<unsigned char>(s[i]);
        if(c<0x80){out+=s[i++];continue;}
        const std::size_t n=c>=0xc2&&c<=0xdf?2:c>=0xe0&&c<=0xef?3:c>=0xf0&&c<=0xf4?4:0;
        std::size_t have=1;
        if(n)for(;have<n && i+have<s.size();++have) {
            const auto d=static_cast<unsigned char>(s[i+have]);
            if(d<0x80||d>0xbf||(have==1&&((c==0xe0&&d<0xa0)||(c==0xed&&d>=0xa0)||(c==0xf0&&d<0x90)||(c==0xf4&&d>=0x90))))break;
        }
        if(n && have==n)out+=s.substr(i,n);else out+="\xef\xbf\xbd";
        i+=have;
    }
    return out;
}
std::string inflate_gzip(const std::string& bytes,std::size_t limit) {
    if(bytes.size()>std::numeric_limits<uInt>::max())throw PartImportError("gzip input too large");
    z_stream stream{};
    if(inflateInit2(&stream,15+16)!=Z_OK)throw PartImportError("cannot initialize gzip decoder");
    struct Guard {z_stream* p;~Guard(){inflateEnd(p);}} guard{&stream};
    stream.next_in=reinterpret_cast<Bytef*>(const_cast<char*>(bytes.data()));stream.avail_in=static_cast<uInt>(bytes.size());
    std::string out;std::array<char,32768> buf{};
    for(;;) {
        stream.next_out=reinterpret_cast<Bytef*>(buf.data());stream.avail_out=static_cast<uInt>(buf.size());
        const int rc=inflate(&stream,Z_NO_FLUSH);
        const auto got=buf.size()-stream.avail_out;
        if(got>limit-out.size())throw PartImportError("decompressed HTTP body exceeds byte limit");
        out.append(buf.data(),got);
        if(rc==Z_STREAM_END) {
            // Python gzip.decompress supports concatenated members and trailing zeros.
            while(stream.avail_in && *stream.next_in==0){++stream.next_in;--stream.avail_in;}
            if(!stream.avail_in)break;
            auto* next=stream.next_in;const auto available=stream.avail_in;
            if(inflateReset2(&stream,15+16)!=Z_OK)throw PartImportError("cannot reset gzip decoder");
            stream.next_in=next;stream.avail_in=available;continue;
        }
        if(rc!=Z_OK || (!got && !stream.avail_in))throw PartImportError("invalid or truncated gzip HTTP body");
    }
    return out;
}
void reject_symlink_chain(const std::filesystem::path& path) {
    std::filesystem::path cursor;
    for(const auto& part:path) {
        if(part==".")continue;
        if(part=="..")throw PartImportError("part root must not contain '..'");
        cursor/=part;
        const auto status=std::filesystem::symlink_status(cursor);
        if(std::filesystem::is_symlink(status))throw PartImportError("refusing symlink in part path: "+cursor.string());
    }
}
std::filesystem::path root_path(const std::filesystem::path& path) {
    if(path.empty())throw PartImportError("parts root must be explicit");
    const auto root=std::filesystem::absolute(path);
    if(root==root.root_path())throw PartImportError("filesystem root is not a parts directory");
    reject_symlink_chain(root);return root.lexically_normal();
}
void validate_plan(const PartImportPlan& plan) {
    const auto& base=plan.part.safe_name;validate_component(base);
    std::set<std::string> needed{base+".kicad_sym",base+".kicad_mod",base+".easyeda.json","part.json"};
    std::set<std::string> seen;
    for(const auto& f:plan.files) {
        if(!needed.count(f.name) && f.name!=base+".wrl" && f.name!=base+".step")throw PartImportError("unrecognized part output: "+f.name);
        if(!seen.insert(f.name).second)throw PartImportError("duplicate part output: "+f.name);
        if(f.bytes.empty())throw PartImportError("empty part output: "+f.name);
    }
    for(const auto& name:needed)if(!seen.count(name))throw PartImportError("missing part output: "+name);
}
}

namespace part_import_detail {
std::string read_file(const std::filesystem::path& path) {
    std::ifstream in(path,std::ios::binary);if(!in)throw PartImportError("cannot read "+path.string());
    std::string out{std::istreambuf_iterator<char>(in),{}};
    if(in.bad())throw PartImportError("cannot read "+path.string());return out;
}
}

PartTransport part_curl_transport(PartProcessRunner runner,const std::string& executable) {
    if(executable.empty() || executable.find('\0')!=executable.npos)throw PartImportError("invalid curl executable");
    if(!runner)runner=[](const auto& argv,auto timeout){return run_process_bytes(argv,timeout);};
    return [runner=std::move(runner),executable](const PartHttpRequest& request) -> PartHttpResponse {
        if(request.url.compare(0,8,"https://")!=0 || request.url.find('\0')!=request.url.npos)
            return {0,{},"only HTTPS URLs are permitted"};
        if(request.timeout.count()<=0 || request.max_bytes==0)return {0,{},"invalid HTTP timeout or byte limit"};
        constexpr const char* marker="\nSCHGEN_HTTP_STATUS:";
        std::ostringstream seconds;seconds.imbue(std::locale::classic());seconds<<request.timeout.count()/1000.0;
        const std::vector<std::string> argv{executable,"--disable","--silent","--show-error","--location","--max-redirs","10",
            "--proto","=https","--proto-redir","=https","--max-time",seconds.str(),"--max-filesize",std::to_string(request.max_bytes),
            "--user-agent",agent,"--write-out",std::string(marker)+"%{http_code}","--url",request.url};
        ProcessResult result;
        try {result=runner(argv,request.timeout+std::chrono::milliseconds(1000));}
        catch(const std::exception& e){return {0,{},e.what()};}
        if(result.exit_code!=0)return {0,{},"curl exit "+std::to_string(result.exit_code)+": "+result.stderr_text};
        const auto pos=result.stdout_text.rfind(marker);
        if(pos==std::string::npos)return {0,{},"curl returned no HTTP status"};
        const auto status=result.stdout_text.substr(pos+std::char_traits<char>::length(marker));
        if(status.size()!=3 || !digits(status))return {0,{},"curl returned invalid HTTP status"};
        return {std::stoi(status),result.stdout_text.substr(0,pos),{}};
    };
}

std::string part_http_body(const PartHttpRequest& request,const PartHttpResponse& response) {
    const std::string prefix="HTTP "+request.url+": ";
    if(!response.transport_error.empty())throw PartImportError(prefix+"transport failed: "+response.transport_error);
    if(response.status<200 || response.status>=300)throw PartImportError(prefix+"status "+std::to_string(response.status));
    if(response.body.size()>request.max_bytes)throw PartImportError(prefix+"body exceeds byte limit");
    try {
        if(response.body.size()>1 && static_cast<unsigned char>(response.body[0])==0x1f && static_cast<unsigned char>(response.body[1])==0x8b)
            return inflate_gzip(response.body,request.max_bytes);
    } catch(const PartImportError& e) {throw PartImportError(prefix+e.what());}
    return response.body;
}

std::string fetch_part_cad(const std::string& lcsc,const PartTransport& transport) {
    validate_url_token(lcsc);if(!transport)throw PartImportError("CAD fetch requires an explicit transport");
    const PartHttpRequest request{"https://easyeda.com/api/products/"+lcsc+"/components?version=6.4.19.5"};
    std::string body;
    try {body=utf8_replace(part_http_body(request,transport(request)));}
    catch(const std::exception& e){throw PartImportError("EasyEDA API unavailable for "+lcsc+": "+e.what()+" — retry or use --from-json");}
    JsonNode payload;
    try{payload=parse_json_text(body,"EasyEDA response");}
    catch(const std::exception& e){throw PartImportError("EasyEDA API returned non-JSON for "+lcsc+": "+e.what());}
    if(!truth(field(payload,"success")) || !object_field(payload,"result"))throw PartImportError("EasyEDA has no CAD data for "+lcsc);
    return body;
}

PartModelDownload fetch_part_models(const std::string& uuid,const std::string& base,const PartTransport& transport) {
    PartModelDownload out;if(uuid.empty())return out;validate_component(base);validate_url_token(uuid);
    if(!transport)throw PartImportError("model fetch requires an explicit transport");
    for(const bool step:{true,false}) {
        const std::string kind=step?"STEP":"OBJ";
        const PartHttpRequest request{std::string("https://modules.easyeda.com/")+(step?"qAxj6KHrDKw4blvCG8QJPs7Y/":"3dmodel/")+uuid};
        try {
            const auto body=part_http_body(request,transport(request));
            if(step) {
                if(body.size()>200 && body.substr(0,100).find("ISO-10303")!=std::string::npos)out.files.push_back({base+".step",body});
                else out.diagnostics.push_back(kind+" asset at "+request.url+" is not a valid STEP payload");
            } else {
                const auto obj=utf8_replace(body);
                if(obj.find("\nv ")==obj.npos) {out.diagnostics.push_back(kind+" asset at "+request.url+" has no OBJ vertices");continue;}
                const auto wrl=model3d_obj_to_wrl(obj);
                if(wrl)out.files.insert(out.files.begin(),{base+".wrl",*wrl});
                else out.diagnostics.push_back(kind+" asset at "+request.url+" has no convertible faces");
            }
        } catch(const std::exception& e) {out.diagnostics.push_back(kind+" asset unavailable: "+e.what());}
    }
    return out;
}

std::vector<std::string> existing_part_models(const std::filesystem::path& parts_root,const std::string& base) {
    validate_component(base);const auto root=root_path(parts_root);const auto dir=root/base;reject_symlink_chain(dir);
    std::vector<std::string> out;
    for(const auto& ext:{".wrl",".step"}) {
        const auto name=base+ext;const auto path=dir/name;const auto status=std::filesystem::symlink_status(path);
        if(std::filesystem::is_symlink(status))throw PartImportError("refusing symlink model cache: "+path.string());
        if(std::filesystem::exists(status)) {
            if(!std::filesystem::is_regular_file(status))throw PartImportError("model cache is not a regular file: "+path.string());
            out.push_back(name);
        }
    }
    return out;
}

std::vector<std::string> publish_part_models(const PartModelDownload& models,const std::filesystem::path& outdir,
                                            const std::string& base,bool overwrite) {
    validate_component(base);
    const auto dir=root_path(outdir);
    std::set<std::string> names;
    for(const auto& f:models.files) {
        if((f.name!=base+".wrl" && f.name!=base+".step") || !names.insert(f.name).second || f.bytes.empty())
            throw PartImportError("invalid downloaded model asset: "+f.name);
        const auto path=dir/f.name;const auto status=std::filesystem::symlink_status(path);
        if(std::filesystem::is_symlink(status) || (std::filesystem::exists(status) && !std::filesystem::is_regular_file(status)))
            throw PartImportError("refusing non-regular model output: "+path.string());
        if(std::filesystem::exists(status) && !overwrite)throw PartImportError("model output already exists (overwrite not enabled): "+path.string());
    }
    if(models.files.empty())return {};
    std::filesystem::create_directories(dir);std::vector<std::string> out;
    for(const auto& f:models.files) {
        try {write_atomic_file((dir/f.name).string(),{f.bytes.begin(),f.bytes.end()});}
        catch(const std::exception& e){throw PartImportError("model publication failed at "+(dir/f.name).string()+"; earlier files may have been published: "+e.what());}
        out.push_back(f.name);
    }
    return out;
}

PartImportPlan prepare_part_import_request(const PartImportRequest& request,const PartTransport& transport) {
    const auto bytes=request.from_json?read_file(*request.from_json):fetch_part_cad(request.lcsc,transport);
    // Validate all core CAD before optional downloads. No partial files on conversion errors.
    auto plan=prepare_part_import(bytes,request.lcsc,request.name);
    const auto existing=existing_part_models(request.parts_root,plan.part.safe_name);
    PartModelDownload downloads;
    if(!request.from_json) {
        const auto payload=parse_json_text(bytes);const auto* wrapped=object_field(payload,"result");
        downloads=fetch_part_models(part_model_uuid(wrapped?*wrapped:payload),plan.part.safe_name,transport);
    }
    plan=prepare_part_import(bytes,request.lcsc,request.name,existing,downloads.files);
    plan.diagnostics.insert(plan.diagnostics.end(),downloads.diagnostics.begin(),downloads.diagnostics.end());return plan;
}

std::filesystem::path publish_part_import(const PartImportPlan& plan,const std::filesystem::path& parts_root,bool overwrite) {
    validate_plan(plan);const auto root=root_path(parts_root);const auto dir=root/plan.part.safe_name;reject_symlink_chain(dir);
    if(std::filesystem::exists(dir) && !std::filesystem::is_directory(dir))throw PartImportError("part output is not a directory: "+dir.string());
    for(const auto& f:plan.files) {
        const auto path=dir/f.name;const auto status=std::filesystem::symlink_status(path);
        if(std::filesystem::is_symlink(status) || (std::filesystem::exists(status) && !std::filesystem::is_regular_file(status)))
            throw PartImportError("refusing non-regular part output: "+path.string());
        if(std::filesystem::exists(status) && !overwrite)throw PartImportError("part output already exists (overwrite not enabled): "+path.string());
    }
    std::filesystem::create_directories(dir);
    for(const auto& f:plan.files) {
        try {write_atomic_file((dir/f.name).string(),{f.bytes.begin(),f.bytes.end()});}
        catch(const std::exception& e){throw PartImportError("part publication failed at "+(dir/f.name).string()+"; earlier files may have been published: "+e.what());}
    }
    return dir;
}

bool compile_imported_part_catalog(const std::filesystem::path& parts_root,const std::filesystem::path& catalog_path) {
    const auto root=root_path(parts_root);
    if(catalog_path.empty())throw PartImportError("catalog destination must be explicit");
    reject_symlink_chain(std::filesystem::absolute(catalog_path));
    return compile_part_catalog(root.string(),catalog_path.string());
}
} // namespace schgen
