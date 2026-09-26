#include <algorithm>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: python_free_tree_contracts REPOSITORY");
        const auto root = fs::canonical(argv[1]);
        if (!fs::is_regular_file(root / "native/CMakeLists.txt"))
            throw std::runtime_error("not a schgen repository: " + root.string());
        std::vector<std::string> problems;
        // Include ignored and hidden paths. Git's object database is history,
        // not the working tree. Do not follow directory symlinks off-tree.
        for (fs::recursive_directory_iterator it(root), end; it != end; ++it) {
            const auto relative = it->path().lexically_relative(root);
            if (relative == ".git") {
                if (it->is_directory()) it.disable_recursion_pending();
                continue;
            }
            const auto extension = it->path().extension().string();
            if (extension == ".py" || extension == ".pyc" || extension == ".pyo")
                problems.push_back(relative.generic_string());
        }
        for (const auto* retired : {"requirements.txt", "pyproject.toml", ".pre-commit-config.yaml", ".venv"}) {
            if (fs::exists(root / retired)) problems.emplace_back(retired);
        }
        std::sort(problems.begin(), problems.end());
        for (const auto& path : problems) std::cerr << "retired Python artifact: " << path << '\n';
        if (!problems.empty()) throw std::runtime_error("repository is not Python-free");
        std::cout << "Python-free working tree: no source, bytecode or retired tooling configuration\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
