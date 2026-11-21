#include "reviewed_ownership.hpp"
#include "schgen/board_definition.hpp"
#include <algorithm>
#include <filesystem>
#include <iostream>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool ok, const std::string& why) {
    ++checks;
    if (!ok) throw std::runtime_error(why);
}
template <class F> void rejects(F f, const std::string& why) {
    bool rejected = false;
    try { f(); } catch (const std::exception&) { rejected = true; }
    require(rejected, "mutation escaped: " + why);
}
JsonNode& mutable_field(JsonNode& n, const std::string& key) {
    for (auto& kv : n.object_value) if (kv.first == key) return kv.second;
    throw std::runtime_error("missing mutation key " + key);
}
PlacementRequirements load(const std::filesystem::path& board, const std::string& sheet) {
    return parse_placement_requirements(parse_json_file((board / "subsystems" / sheet / "placement_requirements.json").string()));
}
void reviewed_matches_data(const std::filesystem::path& board) {
    const auto sheets = load_board_header(board).flags.owned_groups;
    require(!sheets.empty(), "the board names owned-group sheets");
    for (const auto& sheet : sheets) {
        const auto data = load(board, sheet);
        require(data.sheet == sheet, "requirements name their own sheet");
        require(reviewed_ownership::mismatch(data).empty(), "reviewed ownership copy differs from " + sheet + " data: " + reviewed_ownership::mismatch(data));
        const auto want = reviewed_ownership::reviewed(sheet);
        require(data.ownership == want.ownership && data.top_switches == want.top_switches && data.owners == want.owners, "row-for-row equality for " + sheet);
    }
}
void mutations_are_detected(const std::filesystem::path& board) {
    for (const auto& sheet : load_board_header(board).flags.owned_groups) {
        const auto data = load(board, sheet);
        for (std::size_t i = 0; i < data.ownership.size(); ++i) {
            auto dropped = data; dropped.ownership.erase(dropped.ownership.begin() + static_cast<std::ptrdiff_t>(i));
            require(!reviewed_ownership::mismatch(dropped).empty(), "dropped row accepted");
            for (auto field : {&SupplyOwnership::owner, &SupplyOwnership::pin, &SupplyOwnership::pin_name, &SupplyOwnership::cap, &SupplyOwnership::cap_pin,
                               &SupplyOwnership::return_pin, &SupplyOwnership::rail, &SupplyOwnership::return_net, &SupplyOwnership::value, &SupplyOwnership::role}) {
                auto changed = data; changed.ownership[i].*field += "x";
                require(!reviewed_ownership::mismatch(changed).empty(), "changed row field accepted");
            }
        }
        auto extra = data; extra.ownership.push_back(data.ownership.front()); extra.ownership.back().cap = "C99";
        require(!reviewed_ownership::mismatch(extra).empty(), "extra row accepted");
        auto switches = data; switches.top_switches.insert("SW99");
        require(!reviewed_ownership::mismatch(switches).empty(), "extra switch accepted");
        auto fewer = data; fewer.top_switches.erase(fewer.top_switches.begin());
        require(!reviewed_ownership::mismatch(fewer).empty(), "dropped switch accepted");
        for (const auto& owner : data.owners) {
            auto changed = data; changed.owners[owner.first] += "x";
            require(!reviewed_ownership::mismatch(changed).empty(), "changed owner part number accepted");
        }
    }
}
void loader_rejections(const std::filesystem::path& board) {
    const auto sheet = load_board_header(board).flags.owned_groups.front();
    const auto path = (board / "subsystems" / sheet / "placement_requirements.json").string();
    const auto original = parse_json_file(path);
    auto without = original;
    without.object_value.erase(std::remove_if(without.object_value.begin(), without.object_value.end(), [](const auto& kv) { return kv.first == "owners"; }), without.object_value.end());
    rejects([&] { (void)parse_placement_requirements(without); }, "missing owners");
    auto listed = original; mutable_field(listed, "owners").kind = JsonKind::Array;
    rejects([&] { (void)parse_placement_requirements(listed); }, "owners as a list");
    const auto first_owner = load(board, sheet).owners.begin()->first;
    auto empty_mpn = original; mutable_field(mutable_field(empty_mpn, "owners"), first_owner).string_value.clear();
    rejects([&] { (void)parse_placement_requirements(empty_mpn); }, "empty owner part number");
    auto numeric = original; mutable_field(mutable_field(numeric, "owners"), first_owner).kind = JsonKind::Number;
    rejects([&] { (void)parse_placement_requirements(numeric); }, "numeric owner part number");
    JsonNode part_number; part_number.kind = JsonKind::String; part_number.string_value = "PART";
    auto stray = original; mutable_field(stray, "owners").object_value.push_back({"U99", part_number});
    rejects([&] { (void)parse_placement_requirements(stray); }, "owner that owns nothing");
    auto lacking = original; auto& owners = mutable_field(lacking, "owners").object_value; owners.erase(owners.begin());
    rejects([&] { (void)parse_placement_requirements(lacking); }, "owning reference without a part number");
}
}
int main(int argc, char** argv) {
    try {
        require(argc == 3, "usage: ownership_declaration_contracts REPOSITORY BOARD");
        const std::filesystem::path repository = argv[1];
        const auto carrier = repository / argv[2];
        reviewed_matches_data(carrier);
        mutations_are_detected(carrier);
        loader_rejections(carrier);
        std::cout << "PASS " << checks << " ownership declaration assertions\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
