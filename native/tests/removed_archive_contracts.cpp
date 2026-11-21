#include <algorithm>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {
const char* const archive_folder = "removed";
const std::vector<std::string> forbidden_names{"board.json", "project.json"};
const std::vector<std::string> forbidden_extensions{".py", ".pyc", ".pyo"};
const int expected_arguments = 2;
}

int main(int argc, char** argv) {
    try {
        if (argc != expected_arguments) throw std::runtime_error("usage: removed_archive_contracts REPOSITORY");
        const auto root = fs::canonical(argv[1]);
        if (!fs::is_regular_file(root / "native/CMakeLists.txt"))
            throw std::runtime_error("not a schgen repository: " + root.string());
        const auto archive = root / archive_folder;
        if (!fs::is_directory(archive)) throw std::runtime_error("archive folder is missing: " + archive.string());
        if (!fs::is_regular_file(archive / "INDEX.md")) throw std::runtime_error("archive index is missing: removed/INDEX.md");
        std::vector<std::string> problems;
        for (const auto& name : forbidden_names)
            if (fs::exists(archive / name)) problems.push_back(std::string(archive_folder) + "/" + name);
        for (fs::recursive_directory_iterator it(archive), end; it != end; ++it) {
            const auto extension = it->path().extension().string();
            if (std::find(forbidden_extensions.begin(), forbidden_extensions.end(), extension) != forbidden_extensions.end())
                problems.push_back(it->path().lexically_relative(root).generic_string());
        }
        std::sort(problems.begin(), problems.end());
        for (const auto& path : problems) std::cerr << "forbidden archive entry: " << path << '\n';
        if (!problems.empty()) throw std::runtime_error("archive would be read as a board or breaks the Python-free rule");
        std::cout << "archive holds no board.json, project.json or Python file\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
