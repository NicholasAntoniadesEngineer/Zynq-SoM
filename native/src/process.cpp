#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include "schgen/process.hpp"
#include <cerrno>
#include <cstring>
#include <cstdlib>
#include <fcntl.h>
#include <fstream>
#include <spawn.h>
#include <signal.h>
#include <sys/wait.h>
#include <thread>
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
    void close_unrelated() {
#if defined(__GLIBC__) && defined(__GLIBC_PREREQ)
#if __GLIBC_PREREQ(2,34)
        const int code=posix_spawn_file_actions_addclosefrom_np(&value,3);
        if(code)throw ProcessError("cannot close inherited descriptors: "+std::string(std::strerror(code)));
#endif
#endif
    }
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
std::string captured(const std::filesystem::path& path) {
    std::ifstream in(path,std::ios::binary);if(!in)throw ProcessError("cannot read process output");
    const std::string raw{std::istreambuf_iterator<char>(in),{}};if(in.bad())throw ProcessError("cannot read process output");
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
    std::string text;for(std::size_t i=0;i<raw.size();++i){if(raw[i]=='\r'){text+='\n';if(i+1<raw.size()&&raw[i+1]=='\n')++i;}else text+=raw[i];}return text;
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
ProcessResult run_process(const std::vector<std::string>& args,std::chrono::milliseconds timeout) {
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
    return {WIFEXITED(status)?WEXITSTATUS(status):-WTERMSIG(status),captured(scratch.path/"stdout"),captured(scratch.path/"stderr")};
}
}  // namespace schgen
