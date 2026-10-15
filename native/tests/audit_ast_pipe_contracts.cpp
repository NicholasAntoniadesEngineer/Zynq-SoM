#include "schgen/audit_ast_process.hpp"
#include <cerrno>
#include <csignal>
#include <fstream>
#include <iostream>
#include <iterator>
#include <thread>
#include <future>
#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>
#ifdef __APPLE__
#include <libproc.h>
#include <sys/proc.h>
#endif

using namespace schgen;
namespace {
unsigned checks=0;
void need(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
bool running(pid_t pid){
#ifdef __APPLE__
    proc_bsdinfo info{};
    return ::proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&info,sizeof info)==sizeof info&&info.pbi_status!=SZOMB;
#else
    std::ifstream in("/proc/"+std::to_string(pid)+"/stat");std::string line;std::getline(in,line);
    const auto at=line.rfind(')');return at!=std::string::npos&&at+2<line.size()&&line[at+2]!='Z';
#endif
}
std::string all(std::istream& in){return {std::istreambuf_iterator<char>(in),{}};}
std::string result(bool pipe,const std::vector<std::string>& argv,std::chrono::milliseconds timeout=std::chrono::seconds(5)){
    try{
        if(pipe){std::mutex slot;std::unique_lock<std::mutex> lock(slot,std::defer_lock);
            auto r=run_audit_ast_process(argv,"fixture AST",timeout,lock);
            if(r.process.exit_code){need(!r.ast,"nonzero cannot publish provisional AST");return "exit:"+std::to_string(r.process.exit_code)+":"+r.process.stderr_text;}
            need(r.ast.has_value(),"success publishes AST");return "ok:"+std::to_string(static_cast<int>(r.ast->kind));
        }
        auto r=run_process_consume_stdout(argv,[](std::istream& in){(void)parse_audit_ast_projection(in,"fixture AST");},timeout);
        if(r.exit_code)return "exit:"+std::to_string(r.exit_code)+":"+r.stderr_text;
        return "ok:"+std::to_string(static_cast<int>(JsonKind::Object));
    }catch(const ProcessTimeout& e){return "timeout:"+std::string(e.what());}
    catch(const ProcessError& e){return "process:"+std::string(e.what());}
    catch(const std::exception& e){return "parser:"+std::string(e.what());}
}
int emit(unsigned bits,const std::string& report){
    if(!report.empty()){std::ofstream out(report);out<<::getpid()<<'\n';
#ifdef __APPLE__
        char path[4096]{};if(::fcntl(STDERR_FILENO,F_GETPATH,path)>=0)out<<path<<'\n';
#endif
    }
    std::cout<<(bits&1?"{broken":"{\"kind\":\"TranslationUnitDecl\"}");
    if(bits&2){std::cout<<std::string(256*1024,' ')<<char(0xff);}
    if(bits&4)std::cerr<<char(0xff);else std::cerr<<"diagnostic\r\n";
    std::cout.flush();std::cerr.flush();
    if(bits&16)for(;;)::pause();
    if(bits&32)std::raise(SIGTERM);
    return bits&8?9:0;
}
}
int main(int argc,char** argv){try{
    if(argc==2&&std::string(argv[1])=="--probe-fds"){
        for(int fd=3;fd<256;++fd)if(::fcntl(fd,F_GETFD)>=0)return 41;
        std::cout<<"clean";return 0;
    }
    if(argc>=3&&std::string(argv[1])=="--emit")return emit(static_cast<unsigned>(std::stoul(argv[2])),argc>3?argv[3]:"");
    if(argc==3&&std::string(argv[1])=="--bytes"){
        const auto at=static_cast<std::size_t>(std::stoul(argv[2]));
        std::cout<<std::string(at,'a')<<"\xf0\x9f\x98\x80\r\n\rZ\r";return 0;
    }
    if(argc==4&&std::string(argv[1])=="--utf8-at"){
        std::cout<<std::string(static_cast<std::size_t>(std::stoul(argv[2])),'a');const std::string p=argv[3];
        if(p=="surrogate")std::cout<<"\xed\xa0\x80";else if(p=="overlong")std::cout<<"\xe0\x80\x80";
        else if(p=="out-of-range")std::cout<<"\xf4\x90\x80\x80";else if(p=="continuation")std::cout<<"\xe2\x28\xa1";
        else std::cout<<"\xe2\x82";return 0;
    }
    if(argc==4&&std::string(argv[1])=="--sync"){
        std::cout<<"{\"kind\":\"TranslationUnitDecl\"}"<<std::flush;
        for(int i=0;i<200;++i){if(std::filesystem::exists(argv[2])){std::ofstream(argv[3])<<"overlapped";return 0;}
            std::this_thread::sleep_for(std::chrono::milliseconds(5));}
        return 17;
    }
    if(argc==3&&std::string(argv[1])=="--descendant"){
        const auto child=::fork();if(child<0)return 19;
        if(child==0){for(;;)::pause();}
        {std::ofstream out(argv[2]);out<<::getpid()<<' '<<child<<'\n';}
        std::cout<<"{broken"<<std::flush;
        // The OS owns reaping an orphaned grandchild after group cancellation.
        for(;;)::pause();
    }
    const auto exe=std::filesystem::absolute(argv[0]).string();
    // Run each case in a separate process so the test runner's stdio survives.
    // All seven nonempty masks cover original pipe FDs allocated at 0/1/2.
    for(unsigned mask=1;mask<8;++mask){
        const auto pid=::fork();need(pid>=0,"closed stdio fork");
        if(pid==0){
            for(int fd=0;fd<3;++fd)if(mask&(1u<<fd))::close(fd);
            try{std::string bytes;const auto r=run_process_transactional_stdout({exe,"--probe-fds"},[&](std::istream& in){bytes=all(in);});
                ::_exit(r.exit_code==0&&bytes=="clean"?0:42);
            }catch(...){::_exit(43);}
        }
        int status=0;pid_t waited;do{waited=::waitpid(pid,&status,0);}while(waited<0&&errno==EINTR);
        need(waited==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0,"closed stdio remapping / no inherited pipe descriptors");
    }
    // Two concurrent spawn loops exercise sibling descriptor inheritance. No
    // extra global workers or changes to production process policy are needed.
    auto probe=[&]{for(int i=0;i<64;++i){std::string bytes;
        const auto r=run_process_transactional_stdout({exe,"--probe-fds"},[&](std::istream& in){bytes=all(in);});
        if(r.exit_code||bytes!="clean")throw std::runtime_error("sibling inherited a pipe descriptor");
    }};
    auto sibling=std::async(std::launch::async,probe);probe();sibling.get();
    need(true,"128 concurrent sibling spawn probes retain no descriptors");
    auto scratch=(std::filesystem::temp_directory_path()/"schgen_pipe_test_XXXXXX").string();
    need(::mkdtemp(scratch.data())!=nullptr,"mkdtemp");
    struct Cleanup{std::filesystem::path p;~Cleanup(){std::error_code ec;std::filesystem::remove_all(p,ec);}}cleanup{scratch};
    // Every combination: parser failure, late bad stdout, bad stderr, nonzero.
    for(unsigned bits=0;bits<16;++bits){
        const std::vector<std::string> args{exe,"--emit",std::to_string(bits)};
        const auto before=result(false,args),after=result(true,args);
        need(before==after,"failure precedence bits="+std::to_string(bits)+" old="+before+" pipe="+after);
        if(bits&6)need(after=="process:process output is not valid UTF-8","UTF-8 wins over child/parser");
        else if(bits&8)need(after=="exit:9:diagnostic\n","child failure wins over parser");
        else if(bits&1)need(after.rfind("parser:",0)==0,"valid captures expose parser failure");
    }
    for(const unsigned bits:{16u,17u,23u,31u,32u,33u,38u,47u}){
        const auto report=(cleanup.p/"pid").string();
        const std::vector<std::string> args{exe,"--emit",std::to_string(bits),report};
        const auto before=result(false,args,std::chrono::milliseconds(150));
        const auto after=result(true,args,std::chrono::milliseconds(150));
        need(before==after,"timeout/signal precedence "+std::to_string(bits));
        if(bits&16)need(after.rfind("timeout:",0)==0,"timeout beats all output failures");
        int pid=0;std::string scratch_path;std::ifstream probe(report);probe>>pid;probe.ignore();std::getline(probe,scratch_path);
        need(pid>0&&::kill(pid,0)<0&&errno==ESRCH,"direct child reaped before result");
        if(!scratch_path.empty())need(!std::filesystem::exists(std::filesystem::path(scratch_path).parent_path()),"stderr scratch cleaned before result");
    }
    for(int at=65532;at<=65538;++at)for(const auto* payload:{"surrogate","overlong","out-of-range","continuation","truncated"}){
        const std::vector<std::string> args{exe,"--utf8-at",std::to_string(at),payload};
        need(result(false,args)==result(true,args),"invalid UTF-8 scalar/truncation boundary precedence");
    }
    for(const unsigned at:{0u,4095u,4096u,65532u,65533u,65534u,65535u,65536u,65537u,131071u}){
        const std::vector<std::string> args{exe,"--bytes",std::to_string(at)};
        std::string old_text,new_text;
        run_process_consume_stdout(args,[&](std::istream& in){old_text=all(in);});
        run_process_transactional_stdout(args,[&](std::istream& in){new_text=all(in);});
        need(old_text==new_text,"UTF-8 and CRLF chunk boundary parity");
    }
    // Even an early callback return/throw must drain and validate the bad tail.
    for(bool throwing:{false,true}){
        bool invalid=false;
        try{run_process_transactional_stdout({exe,"--emit","2"},[&](std::istream&){if(throwing)throw std::logic_error("sentinel");});}
        catch(const ProcessError& e){invalid=std::string(e.what())=="process output is not valid UTF-8";}
        need(invalid,"unconsumed invalid tail overrides early return/throw");
    }
    // Deterministic overlap proof: child cannot exit until reader has consumed
    // its prefix. The old post-exit consumer would return child failure 17.
    const auto ack=(cleanup.p/"ack").string(),proof=(cleanup.p/"proof").string();
    const auto synced=run_process_transactional_stdout({exe,"--sync",ack,proof},[&](std::istream& in){
        char first=0;in.get(first);need(first=='{',"reader sees live output");std::ofstream(ack)<<"read";
    });
    need(synced.exit_code==0&&std::filesystem::exists(proof),"parser/child overlap is real");
    // Parser execution after child completion does not extend the child timer.
    const auto slow_parser=run_process_transactional_stdout({exe,"--emit","0"},[](std::istream& in){
        (void)all(in);std::this_thread::sleep_for(std::chrono::milliseconds(200));
    },std::chrono::milliseconds(100));
    need(slow_parser.exit_code==0,"child timeout is not a parser deadline");
    const auto family=(cleanup.p/"family").string();
    need(result(true,{exe,"--descendant",family},std::chrono::milliseconds(150)).rfind("timeout:",0)==0,
         "parser failure still waits for timeout and cancels family");
    int parent=0,descendant=0;std::ifstream(family)>>parent>>descendant;
    need(parent>0&&descendant>0&&::kill(parent,0)<0&&errno==ESRCH,"timed-out direct child reaped");
    for(int i=0;i<100&&running(descendant);++i)std::this_thread::sleep_for(std::chrono::milliseconds(2));
    need(!running(descendant),"no running descendant remains after group cancellation");
    for(const auto& args:std::vector<std::vector<std::string>>{{},{""},{"bad\0arg",std::string("x\0y",3)},{"/nonexistent/schgen-pipe"}}){
        bool failed=false;try{run_process_transactional_stdout(args,[](std::istream&){});}catch(const ProcessError&){failed=true;}
        need(failed,"invalid request/spawn failure");
    }
    bool failed=false;try{run_process_transactional_stdout({exe},{ });}catch(const ProcessError&){failed=true;}need(failed,"empty callback");
    failed=false;try{run_process_transactional_stdout({exe},[](std::istream&){},std::chrono::milliseconds(-1));}catch(const ProcessError&){failed=true;}need(failed,"negative timeout");
    std::cout<<"transactional AST pipe contracts PASS checks="<<checks<<" (precedence matrix, reaping, UTF8/newlines, drain, overlap)\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
