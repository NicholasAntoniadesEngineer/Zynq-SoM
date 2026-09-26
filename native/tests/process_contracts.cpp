#include "schgen/process.hpp"
#include <iostream>
#include <fstream>
#include <iterator>
#include <array>
#include <csignal>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
std::string capture_path(){
    std::array<char,4096> name{};
#ifdef __APPLE__
    if(::fcntl(STDOUT_FILENO,F_GETPATH,name.data())<0)throw std::runtime_error("stdout path");
    return name.data();
#else
    const auto n=::readlink("/proc/self/fd/1",name.data(),name.size());if(n<0)throw std::runtime_error("stdout path");
    return {name.data(),static_cast<std::size_t>(n)};
#endif
}
std::string all(std::istream& in){return {std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>()};}
std::string boundary_payload(){
    std::string out(65535,'a');out+="\r\n";out+=std::string(65534,'b');out+="\xc3\xa9\r";
    out+=std::string(65534,'c');out+="\xf0\x9f\x98\x80\r\r\nlast\r";return out;
}
void consumer_contracts(const std::string& executable){
    std::size_t checks=0;const auto require=[&](bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);};
    const auto consume=[&](const std::string& mode){std::string text;int calls=0;const auto r=schgen::run_process_consume_stdout({executable,mode},[&](std::istream& in){++calls;text=all(in);});require(r.exit_code==0&&calls==1,"successful consumer called exactly once");return text;};
    require(consume("--emit-text")==schgen::run_process({executable,"--emit-text"}).stdout_text,"consumer universal newlines");
    require(consume("--emit-large")==schgen::run_process({executable,"--emit-large"}).stdout_text,"consumer 8 MiB text parity");
    require(consume("--emit-boundaries")==schgen::run_process({executable,"--emit-boundaries"}).stdout_text,"UTF-8 and CRLF across chunk boundaries");
    require(consume("--emit-nul")==std::string("a\0b\n",4),"valid UTF-8 may contain embedded NUL");
    for(const auto* mode:{"--emit-bytes","--bad-stderr","--bad-tail","--truncated-utf8"}){
        bool called=false,rejected=false;try{schgen::run_process_consume_stdout({executable,mode},[&](std::istream&){called=true;});}catch(const schgen::ProcessError&){rejected=true;}
        require(rejected&&!called,std::string("complete UTF-8 validates before any consumer side effect: ")+mode);
    }
    for(int offset=65532;offset<=65538;++offset)for(const auto* payload:{"ok","surrogate","overlong","out-of-range","continuation","truncated"}){
        const bool valid=std::string(payload)=="ok";bool called=false,rejected=false;
        try{schgen::run_process_consume_stdout({executable,"--utf8-at",std::to_string(offset),payload},[&](std::istream& in){called=true;require(!all(in).empty(),"valid boundary text");});}catch(const schgen::ProcessError&){rejected=true;}
        require(valid?called&&!rejected:!called&&rejected,"strict UTF-8 scalar boundary matrix");
    }
    bool called=false;
    const auto failed=schgen::run_process_consume_stdout({executable,"--valid-failure"},[&](std::istream&){called=true;});
    require(!called&&failed.exit_code==9&&failed.stderr_text=="diagnostic\n","failed child does not parse partial stdout; diagnostics preserved");
    const auto signalled=schgen::run_process_consume_stdout({executable,"--signal"},[&](std::istream&){called=true;});
    require(!called&&signalled.exit_code==-SIGTERM,"signed signal return preserved");
    std::filesystem::path captured;
    const auto inspect=[&](std::istream& in){std::string value;std::getline(in,value);captured=value;
        require(std::filesystem::is_regular_file(captured),"capture exists during callback");
        struct stat status{};require(::stat(captured.parent_path().c_str(),&status)==0&&(status.st_mode&0777)==0700,"capture directory private 0700");
        require(::stat(captured.c_str(),&status)==0&&(status.st_mode&0777)==0600,"capture file private 0600");};
    (void)schgen::run_process_consume_stdout({executable,"--capture-path"},inspect);
    require(!captured.empty()&&!std::filesystem::exists(captured.parent_path()),"success cleans capture after consumer");
    bool thrown=false;try{schgen::run_process_consume_stdout({executable,"--capture-path"},[&](std::istream& in){inspect(in);throw std::logic_error("consumer sentinel");});}catch(const std::logic_error& e){thrown=std::string(e.what())=="consumer sentinel";}
    require(thrown&&!std::filesystem::exists(captured.parent_path()),"consumer exception preserved and scratch cleaned");
    auto temp=(std::filesystem::temp_directory_path()/"schgen_process_contract_XXXXXX").string();
    require(::mkdtemp(temp.data())!=nullptr,"private timeout probe directory");
    struct Cleanup {std::filesystem::path p;~Cleanup(){std::error_code e;std::filesystem::remove_all(p,e);}} cleanup{temp};
    const auto report=(cleanup.p/"child.txt").string();bool timeout=false;
    try{schgen::run_process_consume_stdout({executable,"--wait",report},[&](std::istream&){called=true;},std::chrono::milliseconds{300});}catch(const schgen::ProcessTimeout&){timeout=true;}
    require(timeout&&!called,"timeout never calls consumer");
    std::ifstream probe(report);std::string path;int pid=0;std::getline(probe,path);probe>>pid;
    require(!path.empty()&&pid>0&&!std::filesystem::exists(std::filesystem::path(path).parent_path()),"timeout cleans private capture");
    require(::kill(pid,0)<0&&errno==ESRCH,"timed-out child was killed and reaped");
    for(const auto& args:std::vector<std::vector<std::string>>{{},{""},{std::string("bad\0arg",7)},{"/nonexistent/process-consumer"}}){
        bool rejected=false;try{schgen::run_process_consume_stdout(args,[](std::istream&){});}catch(const schgen::ProcessError&){rejected=true;}require(rejected,"invalid executable/arguments reject");}
    bool empty=false;try{schgen::run_process_consume_stdout({executable},{});}catch(const schgen::ProcessError&){empty=true;}require(empty,"empty consumer rejects");
    bool negative=false;try{schgen::run_process_consume_stdout({executable},[](std::istream&){},std::chrono::milliseconds{-1});}catch(const schgen::ProcessError&){negative=true;}require(negative,"negative timeout rejects");
    std::cout<<checks<<" scoped stdout consumer contracts passed\n";
}
}

int main(int argc,char** argv){
    const std::string bytes{static_cast<char>(0xff),'\0','\r','\n',static_cast<char>(0x1f),static_cast<char>(0x8b)};
    if(argc==2&&std::string(argv[1])=="--capture-path"){std::cout<<capture_path()<<'\n';return 0;}
    if(argc==2&&std::string(argv[1])=="--emit-boundaries"){std::cout<<boundary_payload();return 0;}
    if(argc==2&&std::string(argv[1])=="--emit-nul"){std::cout.write("a\0b\r\n",5);return 0;}
    if(argc==2&&std::string(argv[1])=="--bad-stderr"){std::cout<<"valid";std::cerr<<char(0xff);return 0;}
    if(argc==2&&std::string(argv[1])=="--bad-tail"){std::cout<<std::string(131072,'a')<<char(0xff);return 0;}
    if(argc==2&&std::string(argv[1])=="--truncated-utf8"){std::cout<<std::string(65535,'a')<<"\xf0\x9f";return 0;}
    if(argc==2&&std::string(argv[1])=="--valid-failure"){std::cout<<"{ partial";std::cerr<<"diagnostic\r\n";return 9;}
    if(argc==2&&std::string(argv[1])=="--signal"){std::raise(SIGTERM);return 99;}
    if(argc==3&&std::string(argv[1])=="--wait"){{std::ofstream out(argv[2]);out<<capture_path()<<'\n'<<::getpid()<<'\n';}for(;;)::pause();}
    if(argc==4&&std::string(argv[1])=="--utf8-at"){
        std::cout<<std::string(static_cast<std::size_t>(std::stoul(argv[2])),'a');const std::string p=argv[3];
        if(p=="ok")std::cout<<"\xf0\x9f\x98\x80";else if(p=="surrogate")std::cout<<"\xed\xa0\x80";
        else if(p=="overlong")std::cout<<"\xe0\x80\x80";else if(p=="out-of-range")std::cout<<"\xf4\x90\x80\x80";
        else if(p=="continuation")std::cout<<"\xe2\x28\xa1";else std::cout<<"\xe2\x82";return 0;
    }
    if(argc==2&&std::string(argv[1])=="--emit-bytes"){
        std::cout.write(bytes.data(),static_cast<std::streamsize>(bytes.size()));
        std::cerr.write(bytes.data(),static_cast<std::streamsize>(bytes.size()));return 7;
    }
    if(argc==2&&std::string(argv[1])=="--emit-text"){
        std::cout<<"one\r\ntwo\rthree\n";return 0;
    }
    if(argc==2&&std::string(argv[1])=="--emit-large"){
        const std::string block(8*1024*1024,'x');
        std::cout.write(block.data(),static_cast<std::streamsize>(block.size()));
        std::cout<<"\r\n\rUTF-8: \xc3\xa9\n";return 0;
    }
    try{
        const auto executable=std::filesystem::absolute(argv[0]).string();
        const auto binary=schgen::run_process_bytes({executable,"--emit-bytes"});
        if(binary.exit_code!=7||binary.stdout_text!=bytes||binary.stderr_text!=bytes)
            throw std::runtime_error("binary transport changed bytes or exit status");
        bool rejected=false;
        try{schgen::run_process({executable,"--emit-bytes"});}catch(const schgen::ProcessError&){rejected=true;}
        if(!rejected)throw std::runtime_error("text transport accepted invalid UTF-8");
        const auto text=schgen::run_process({executable,"--emit-text"});
        if(text.exit_code||text.stdout_text!="one\ntwo\nthree\n")
            throw std::runtime_error("legacy universal-newline text semantics changed");
        if(schgen::run_process_bytes({executable,"--emit-text"}).stdout_text!="one\r\ntwo\rthree\n")
            throw std::runtime_error("binary transport normalized CRLF");
        const auto large=schgen::run_process({executable,"--emit-large"});
        if(large.exit_code||large.stdout_text!=std::string(8*1024*1024,'x')+"\n\nUTF-8: \xc3\xa9\n")
            throw std::runtime_error("large text capture changed payload or UTF-8/newline semantics");
        std::cout<<"Native process text/binary contracts passed\n";
        consumer_contracts(executable);
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
