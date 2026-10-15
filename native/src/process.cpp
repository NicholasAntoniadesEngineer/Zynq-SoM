#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include "schgen/process.hpp"
#include <cerrno>
#include <array>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <fcntl.h>
#include <fstream>
#include <limits>
#include <spawn.h>
#include <signal.h>
#include <streambuf>
#include <sys/wait.h>
#include <thread>
#include <atomic>
#include <future>
#include <poll.h>
#include <unistd.h>

extern char** environ;
namespace schgen {
namespace {
struct Scratch {
    std::filesystem::path path;
    Scratch(){auto pattern=(std::filesystem::temp_directory_path()/"schgen_process_XXXXXX").string();if(!::mkdtemp(pattern.data()))throw ProcessError("cannot create process scratch: "+std::string(std::strerror(errno)));path=pattern;}
    ~Scratch(){std::error_code error;std::filesystem::remove_all(path,error);}
};
struct Actions {
    posix_spawn_file_actions_t value;
    Actions(){const int code=posix_spawn_file_actions_init(&value);if(code)throw ProcessError(std::strerror(code));}
    ~Actions(){posix_spawn_file_actions_destroy(&value);}
    void open(int fd,const std::filesystem::path& path,int flags){const int code=posix_spawn_file_actions_addopen(&value,fd,path.c_str(),flags,0600);if(code)throw ProcessError("cannot redirect process: "+std::string(std::strerror(code)));}
    void duplicate(int from,int to){const int code=posix_spawn_file_actions_adddup2(&value,from,to);if(code)throw ProcessError("cannot redirect pipe: "+std::string(std::strerror(code)));}
    void close_unrelated() {
#if defined(__GLIBC__) && defined(__GLIBC_PREREQ)
#if __GLIBC_PREREQ(2,34)
        const int code=posix_spawn_file_actions_addclosefrom_np(&value,3);
        if(code)throw ProcessError("cannot close inherited descriptors: "+std::string(std::strerror(code)));
#endif
#endif
    }
};
struct Pipe {
    int read_fd=-1,write_fd=-1;
    Pipe(){
        int fds[2];
#ifdef __linux__
        // Atomic from creation: before F_DUPFD_CLOEXEC below, a concurrent
        // spawn must not inherit either original descriptor on older glibc
        // without closefrom. Do not fall back to racy pipe()+fcntl on ENOSYS.
        if(::pipe2(fds,O_CLOEXEC))throw ProcessError("cannot create stdout pipe");
#else
        if(::pipe(fds))throw ProcessError("cannot create stdout pipe");
#endif
        read_fd=fds[0];write_fd=fds[1];
        // Keep redirection descriptors above stdin/stdout/stderr even when the
        // caller has closed one of those. CLOEXEC prevents sibling inheritance.
        for(int* fd:{&read_fd,&write_fd}){
            const int owned=::fcntl(*fd,F_DUPFD_CLOEXEC,3);
            if(owned<0){close();throw ProcessError("cannot isolate stdout pipe");}
            ::close(*fd);*fd=owned;
        }
        if(::fcntl(read_fd,F_SETFL,O_NONBLOCK)<0){close();throw ProcessError("cannot configure stdout pipe");}
    }
    void close(){if(read_fd>=0)::close(read_fd);if(write_fd>=0)::close(write_fd);read_fd=write_fd=-1;}
    void close_writer(){::close(write_fd);write_fd=-1;}
    ~Pipe(){close();}
};
// Incremental raw-byte validation; remember failure but keep draining, so a
// later child timeout or earlier stderr/exit boundary keeps its old precedence.
struct PipeUtf8 {
    unsigned need=0;std::uint32_t cp=0,minimum=0;bool invalid=false;
    void feed(const char* bytes,std::size_t size){
        if(invalid)return;
        for(std::size_t i=0;i<size;){
            if(!need&&size-i>=sizeof(std::uint64_t)){
                std::uint64_t word=0;std::memcpy(&word,bytes+i,sizeof word);
                if(!(word&UINT64_C(0x8080808080808080))){i+=sizeof word;continue;}
            }
            const auto c=static_cast<unsigned char>(bytes[i++]);
            if(need){if((c&0xc0)!=0x80){invalid=true;return;}cp=(cp<<6)|(c&0x3f);
                if(!--need&&(cp<minimum||cp>0x10ffffu||(cp>=0xd800u&&cp<=0xdfffu))){invalid=true;return;}
            }else if(c<0x80)continue;
            else if(c>=0xc2&&c<=0xdf){need=1;cp=c&0x1f;minimum=0x80;}
            else if(c>=0xe0&&c<=0xef){need=2;cp=c&0x0f;minimum=0x800;}
            else if(c>=0xf0&&c<=0xf4){need=3;cp=c&7;minimum=0x10000;}
            else{invalid=true;return;}
        }
    }
};
class TransactionalPipe final:public std::streambuf {
public:
    TransactionalPipe(int fd,const std::atomic<bool>& finished):fd_(fd),finished_(finished){}
    PipeUtf8 utf8;
    void drain(){setg(nullptr,nullptr,nullptr);while(underflow()!=traits_type::eof())setg(nullptr,nullptr,nullptr);}
protected:
    int_type underflow()override{
        if(gptr()!=egptr())return traits_type::to_int_type(*gptr());
        for(;;){
            // Observe completion BEFORE read: the child's last write can race
            // an earlier EAGAIN. Once completion is acquired, read sees all
            // remaining bytes or real EOF before classifying a live writer.
            const bool completed=finished_.load(std::memory_order_acquire);
            const auto n=::read(fd_,bytes_.data(),bytes_.size());
            if(n==0)return traits_type::eof();
            if(n<0){
                if(errno==EINTR)continue;
                if(errno!=EAGAIN&&errno!=EWOULDBLOCK)throw ProcessError("cannot read process output");
                // A surviving writer is not EOF. Never accept a provisional
                // AST while an escaped descendant could still append bytes.
                if(completed)throw ProcessError("process stdout pipe remained open after child exit");
                pollfd ready{fd_,POLLIN,0};
                if(::poll(&ready,1,10)<0&&errno!=EINTR)throw ProcessError("cannot read process output");
                continue;
            }
            const auto size=static_cast<std::size_t>(n);utf8.feed(bytes_.data(),size);
            std::size_t written=size;
            if(skip_lf_||std::memchr(bytes_.data(),'\r',size)){
                const std::size_t first=skip_lf_&&bytes_[0]=='\n'?1:0;skip_lf_=false;written=0;
                for(std::size_t i=first;i<size;++i){
                    if(bytes_[i]=='\r'){bytes_[written++]='\n';
                        if(i+1<size&&bytes_[i+1]=='\n')++i;else if(i+1==size)skip_lf_=true;
                    }else bytes_[written++]=bytes_[i];
                }
            }
            if(written){setg(bytes_.data(),bytes_.data(),bytes_.data()+written);return traits_type::to_int_type(*gptr());}
        }
    }
private:
    int fd_;const std::atomic<bool>& finished_;
    std::array<char,65536> bytes_{};bool skip_lf_=false;
};
struct Attributes {
    posix_spawnattr_t value;
    Attributes(){const int code=posix_spawnattr_init(&value);if(code)throw ProcessError(std::strerror(code));}
    ~Attributes(){posix_spawnattr_destroy(&value);}
    void isolate(){short flags=POSIX_SPAWN_SETPGROUP;
#ifdef POSIX_SPAWN_CLOEXEC_DEFAULT
        flags|=POSIX_SPAWN_CLOEXEC_DEFAULT;
#endif
        int code=posix_spawnattr_setpgroup(&value,0);if(!code)code=posix_spawnattr_setflags(&value,flags);if(code)throw ProcessError("cannot isolate process group: "+std::string(std::strerror(code)));}
};
struct Child {
    pid_t pid=-1;
    ~Child(){if(pid>0){::kill(-pid,SIGKILL);int status=0;while(::waitpid(pid,&status,0)<0&&errno==EINTR){}}}
};
// Validate complete text without retaining it or trusting how much a consumer
// chooses to read. UTF-8 scalars may cross any capture-buffer boundary.
void validate_capture_utf8(const std::filesystem::path& path){
    std::ifstream in(path,std::ios::binary);if(!in)throw ProcessError("cannot read process output");
    std::array<char,65536> bytes{};unsigned need=0;std::uint32_t cp=0,minimum=0;
    const auto invalid=[](){throw ProcessError("process output is not valid UTF-8");};
    for(;;){
        in.read(bytes.data(),static_cast<std::streamsize>(bytes.size()));const auto size=static_cast<std::size_t>(in.gcount());
        if(in.bad()||(in.fail()&&!in.eof()))throw ProcessError("cannot read process output");
        for(std::size_t i=0;i<size;){
            if(!need&&size-i>=sizeof(std::uint64_t)){
                std::uint64_t word=0;std::memcpy(&word,bytes.data()+i,sizeof word);
                if(!(word&UINT64_C(0x8080808080808080))){i+=sizeof word;continue;}
            }
            const auto c=static_cast<unsigned char>(bytes[i++]);
            if(need){if((c&0xc0)!=0x80)invalid();cp=(cp<<6)|(c&0x3f);
                if(!--need&&(cp<minimum||cp>0x10ffffu||(cp>=0xd800u&&cp<=0xdfffu)))invalid();
            }else if(c<0x80)continue;
            else if(c>=0xc2&&c<=0xdf){need=1;cp=c&0x1f;minimum=0x80;}
            else if(c>=0xe0&&c<=0xef){need=2;cp=c&0x0f;minimum=0x800;}
            else if(c>=0xf0&&c<=0xf4){need=3;cp=c&7;minimum=0x10000;}
            else invalid();
        }
        if(in.eof())break;
    }
    if(need)invalid();
}
class NormalizedCapture final:public std::streambuf {
public:
    explicit NormalizedCapture(const std::filesystem::path& path):input_(path,std::ios::binary){
        if(!input_)throw ProcessError("cannot read process output");
    }
protected:
    int_type underflow()override{
        if(gptr()!=egptr())return traits_type::to_int_type(*gptr());
        for(;;){
            input_.read(bytes_.data(),static_cast<std::streamsize>(bytes_.size()));const auto size=static_cast<std::size_t>(input_.gcount());
            if(input_.bad()||(input_.fail()&&!input_.eof()))throw ProcessError("cannot read process output");
            if(!size)return traits_type::eof();
            std::size_t written=size;
            if(skip_lf_||std::memchr(bytes_.data(),'\r',size)){
                const std::size_t first=skip_lf_&&bytes_[0]=='\n'?1:0;skip_lf_=false;written=0;
                for(std::size_t i=first;i<size;++i){
                    if(bytes_[i]=='\r'){
                        bytes_[written++]='\n';
                        if(i+1<size&&bytes_[i+1]=='\n')++i;
                        else if(i+1==size)skip_lf_=true;
                    }else bytes_[written++]=bytes_[i];
                }
            }
            if(written){setg(bytes_.data(),bytes_.data(),bytes_.data()+written);return traits_type::to_int_type(*gptr());}
        }
    }
private:
    std::ifstream input_;
    std::array<char,65536> bytes_{};
    bool skip_lf_=false;
};
std::string captured(const std::filesystem::path& path,bool binary) {
    // The child has exited and this private capture file is complete. Size it
    // once and read in bulk: compiler ASTs can exceed a gigabyte, for which
    // iterator growth plus a second normalized copy is prohibitively costly.
    std::ifstream in(path,std::ios::binary|std::ios::ate);if(!in)throw ProcessError("cannot read process output");
    const std::streamoff length=in.tellg();
    std::string raw;
    if(length<0||static_cast<std::uintmax_t>(length)>raw.max_size()||
       static_cast<std::uintmax_t>(length)>static_cast<std::uintmax_t>(std::numeric_limits<std::streamsize>::max()))
        throw ProcessError("process output size cannot be represented");
    raw.resize(static_cast<std::size_t>(length));in.seekg(0);
    if(!in||(length&&!in.read(raw.data(),static_cast<std::streamsize>(length))))throw ProcessError("cannot read process output");
    if(binary)return raw;
    // Match subprocess text=True's strict UTF-8 decoding. Invalid output must
    // not be silently searched for a measurement and credited as a cross-check.
    for(std::size_t i=0;i<raw.size();) {
        const auto a=static_cast<unsigned char>(raw[i]);if(a<0x80){++i;continue;}
        const std::size_t n=a>=0xc2&&a<=0xdf?2:a>=0xe0&&a<=0xef?3:a>=0xf0&&a<=0xf4?4:0;
        bool valid=n&&i+n<=raw.size();
        for(std::size_t j=1;valid&&j<n;++j){const auto b=static_cast<unsigned char>(raw[i+j]);valid=(b&0xc0)==0x80;
            if(j==1&&((a==0xe0&&b<0xa0)||(a==0xed&&b>=0xa0)||(a==0xf0&&b<0x90)||(a==0xf4&&b>=0x90)))valid=false;}
        if(!valid)throw ProcessError("process output is not valid UTF-8");i+=n;
    }
    const auto first=raw.find('\r');
    if(first==std::string::npos)return raw;
    std::size_t written=first;
    for(std::size_t i=first;i<raw.size();++i){
        if(raw[i]=='\r'){raw[written++]='\n';if(i+1<raw.size()&&raw[i+1]=='\n')++i;}
        else raw[written++]=raw[i];
    }
    raw.resize(written);return raw;
}
}
std::optional<std::filesystem::path> find_executable(const std::string& command) {
    if(command.empty()||command.find('\0')!=std::string::npos)return std::nullopt;
    auto usable=[](const std::filesystem::path& path){return std::filesystem::is_regular_file(path)&&::access(path.c_str(),X_OK)==0;};
    if(command.find('/')!=std::string::npos)return usable(command)?std::optional<std::filesystem::path>(command):std::nullopt;
    const auto* env=std::getenv("PATH");const std::string paths=env?env:"/usr/bin:/bin";
    std::size_t begin=0;for(;;){const auto end=paths.find(':',begin);const auto dir=paths.substr(begin,end==std::string::npos?end:end-begin);
        const auto candidate=std::filesystem::path(dir)/command;if(usable(candidate))return candidate;
        if(end==std::string::npos)break;begin=end+1;
    }return std::nullopt;
}
static ProcessResult run_process_impl(const std::vector<std::string>& args,std::chrono::milliseconds timeout,bool binary,
    const ProcessStdoutConsumer* consumer=nullptr) {
    if(args.empty()||args.front().empty())throw ProcessError("process executable is empty");
    for(const auto& arg:args)if(arg.find('\0')!=std::string::npos)throw ProcessError("embedded null byte in process argument");
    if(timeout.count()<0)throw ProcessError("process timeout must not be negative");
    Scratch scratch;Actions actions;Attributes attrs;attrs.isolate();
    actions.open(STDIN_FILENO,"/dev/null",O_RDONLY);actions.open(STDOUT_FILENO,scratch.path/"stdout",O_WRONLY|O_CREAT|O_TRUNC);actions.open(STDERR_FILENO,scratch.path/"stderr",O_WRONLY|O_CREAT|O_TRUNC);
    actions.close_unrelated();
    std::vector<char*> argv;for(const auto& arg:args)argv.push_back(const_cast<char*>(arg.c_str()));argv.push_back(nullptr);
    Child child;const int error=::posix_spawnp(&child.pid,argv.front(),&actions.value,&attrs.value,argv.data(),environ);
    if(error){child.pid=-1;throw ProcessError("cannot execute "+args.front()+": "+std::strerror(error));}
    const auto deadline=std::chrono::steady_clock::now()+timeout;int status=0;
    for(;;){const auto result=::waitpid(child.pid,&status,WNOHANG);if(result==child.pid){child.pid=-1;break;}
        if(result<0){if(errno==EINTR)continue;throw ProcessError("cannot wait for process: "+std::string(std::strerror(errno)));}
        if(std::chrono::steady_clock::now()>=deadline)throw ProcessTimeout("process timed out after "+std::to_string(timeout.count())+" ms: "+args.front());
        std::this_thread::sleep_for(std::chrono::milliseconds{2});
    }
    const auto code=WIFEXITED(status)?WEXITSTATUS(status):-WTERMSIG(status);
    if(consumer){
        validate_capture_utf8(scratch.path/"stdout");
        auto errors=captured(scratch.path/"stderr",false);
        if(code==0){
            NormalizedCapture buffer(scratch.path/"stdout");std::istream input(&buffer);
            input.exceptions(std::ios::badbit);(*consumer)(input);
            if(input.bad())throw ProcessError("cannot read process output");
        }
        return {code,{},std::move(errors)};
    }
    return {code,captured(scratch.path/"stdout",binary),captured(scratch.path/"stderr",binary)};
}
ProcessResult run_process(const std::vector<std::string>& args,std::chrono::milliseconds timeout){return run_process_impl(args,timeout,false);}
ProcessResult run_process_bytes(const std::vector<std::string>& args,std::chrono::milliseconds timeout){return run_process_impl(args,timeout,true);}
ProcessConsumedResult run_process_consume_stdout(const std::vector<std::string>& args,const ProcessStdoutConsumer& consumer,std::chrono::milliseconds timeout){
    if(!consumer)throw ProcessError("process stdout consumer is empty");
    auto result=run_process_impl(args,timeout,false,&consumer);return {result.exit_code,std::move(result.stderr_text)};
}
ProcessConsumedResult run_process_transactional_stdout(const std::vector<std::string>& args,const ProcessStdoutConsumer& consumer,std::chrono::milliseconds timeout){
    if(!consumer)throw ProcessError("process stdout consumer is empty");
    if(args.empty()||args.front().empty())throw ProcessError("process executable is empty");
    for(const auto& arg:args)if(arg.find('\0')!=std::string::npos)throw ProcessError("embedded null byte in process argument");
    if(timeout.count()<0)throw ProcessError("process timeout must not be negative");
    Scratch scratch;Pipe pipe;Actions actions;Attributes attrs;attrs.isolate();
    actions.open(STDIN_FILENO,"/dev/null",O_RDONLY);actions.duplicate(pipe.write_fd,STDOUT_FILENO);
    actions.open(STDERR_FILENO,scratch.path/"stderr",O_WRONLY|O_CREAT|O_TRUNC);actions.close_unrelated();
    std::vector<char*> argv;for(const auto& arg:args)argv.push_back(const_cast<char*>(arg.c_str()));argv.push_back(nullptr);
    Child child;const int error=::posix_spawnp(&child.pid,argv.front(),&actions.value,&attrs.value,argv.data(),environ);
    if(error){child.pid=-1;throw ProcessError("cannot execute "+args.front()+": "+std::strerror(error));}
    pipe.close_writer();
    const auto deadline=std::chrono::steady_clock::now()+timeout;
    std::atomic<bool> finished{false};
    // A separate reaper keeps the child timeout live while the parser is busy
    // or blocked in a read. Its future is always joined before state unwinds.
    auto reaper=std::async(std::launch::async,[&]{
        struct Done{std::atomic<bool>& flag;~Done(){flag.store(true,std::memory_order_release);}} done{finished};
        int status=0;const auto pid=child.pid;
        try{
            for(;;){const auto result=::waitpid(pid,&status,WNOHANG);if(result==pid){child.pid=-1;::kill(-pid,SIGKILL);break;}
                if(result<0){if(errno==EINTR)continue;throw ProcessError("cannot wait for process: "+std::string(std::strerror(errno)));}
                if(std::chrono::steady_clock::now()>=deadline)throw ProcessTimeout("process timed out after "+std::to_string(timeout.count())+" ms: "+args.front());
                std::this_thread::sleep_for(std::chrono::milliseconds{2});
            }
        }catch(...){::kill(-pid,SIGKILL);while(::waitpid(pid,&status,0)<0&&errno==EINTR){}child.pid=-1;throw;}
        return WIFEXITED(status)?WEXITSTATUS(status):-WTERMSIG(status);
    });
    TransactionalPipe buffer(pipe.read_fd,finished);std::istream input(&buffer);input.exceptions(std::ios::badbit);
    std::exception_ptr parser_error,read_error;
    try{consumer(input);if(input.bad())throw ProcessError("cannot read process output");}catch(...){parser_error=std::current_exception();}
    try{buffer.drain();}catch(...){read_error=std::current_exception();}
    const int code=reaper.get(); // timeout/wait failure wins, just as before
    if(read_error)std::rethrow_exception(read_error);
    if(buffer.utf8.invalid||buffer.utf8.need)throw ProcessError("process output is not valid UTF-8");
    auto errors=captured(scratch.path/"stderr",false);
    if(code==0&&parser_error)std::rethrow_exception(parser_error);
    return {code,std::move(errors)};
}
}  // namespace schgen
