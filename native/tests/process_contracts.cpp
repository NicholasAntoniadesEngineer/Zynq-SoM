#include "schgen/process.hpp"
#include <iostream>

int main(int argc,char** argv){
    const std::string bytes{static_cast<char>(0xff),'\0','\r','\n',static_cast<char>(0x1f),static_cast<char>(0x8b)};
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
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
