#include "schgen/study.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <set>
#include <sstream>
#include <stdexcept>

namespace schgen::study {
namespace {

[[noreturn]] void fail(const std::string& what) { throw std::runtime_error("study layers: " + what); }

std::string shown(double value) {
    std::ostringstream text;
    text << value;
    return text.str();
}

JsonNode nothing() { return {}; }

JsonNode number(double value) {
    JsonNode node;
    node.kind = JsonKind::Number;
    node.number_value = value;
    return node;
}

JsonNode string(const std::string& value) {
    JsonNode node;
    node.kind = JsonKind::String;
    node.string_value = value;
    return node;
}

JsonNode list(std::vector<JsonNode> values) {
    JsonNode node;
    node.kind = JsonKind::Array;
    node.array_value = std::move(values);
    return node;
}

JsonNode object(std::vector<std::pair<std::string, JsonNode>> fields) {
    JsonNode node;
    node.kind = JsonKind::Object;
    node.object_value = std::move(fields);
    return node;
}

std::string quoted(const std::string& value) {
    std::string out = "\"";
    for (const char letter : value) {
        if (letter == '"' || letter == '\\') out += std::string("\\") + letter;
        else if (letter == '\n') out += "\\n";
        else if (letter == '\t') out += "\\t";
        else if (letter == '\r') out += "\\r";
        else if (static_cast<unsigned char>(letter) < static_cast<unsigned char>(' ')) fail("a report holds a control character");
        else out += letter;
    }
    return out + "\"";
}

std::string written(const JsonNode& node, const std::string& indent) {
    const std::string inner = indent + " ";
    switch (node.kind) {
    case JsonKind::Null: return "null";
    case JsonKind::Bool: return node.bool_value ? "true" : "false";
    case JsonKind::Number: return shown(node.number_value);
    case JsonKind::String: return quoted(node.string_value);
    case JsonKind::Array: {
        if (node.array_value.empty()) return "[]";
        std::string out = "[";
        for (std::size_t index = 0; index < node.array_value.size(); ++index)
            out += std::string(index ? "," : "") + "\n" + inner + written(node.array_value[index], inner);
        return out + "\n" + indent + "]";
    }
    case JsonKind::Object: {
        if (node.object_value.empty()) return "{}";
        std::string out = "{";
        for (std::size_t index = 0; index < node.object_value.size(); ++index)
            out += std::string(index ? "," : "") + "\n" + inner + quoted(node.object_value[index].first) + ": " +
                   written(node.object_value[index].second, inner);
        return out + "\n" + indent + "}";
    }
    }
    throw std::logic_error("unknown JSON kind");
}

class Words {
public:
    Words(const std::string& line, std::string report) : in_(line), line_(line), report_(std::move(report)) {}
    void expect(const std::string& word) {
        std::string got;
        if (!(in_ >> got) || got != word) broken();
    }
    double number() {
        double value = 0;
        if (!(in_ >> value)) broken();
        return value;
    }

private:
    [[noreturn]] void broken() const { fail(report_ + " line is not in the expected form: " + line_); }
    std::istringstream in_;
    std::string line_, report_;
};

std::string line_of(const std::string& report, const std::string& prefix) {
    std::istringstream lines(report);
    std::string line, found;
    std::size_t count = 0;
    while (std::getline(lines, line))
        if (line.rfind(prefix, 0) == 0) {
            found = line;
            ++count;
        }
    if (count != 1) fail(std::string(squeeze_report) + " holds " + std::to_string(count) + " lines starting '" + prefix + "'");
    return found;
}

std::string size_text(double width, double height) { return shown(width) + " x " + shown(height); }

Cell pair_cell(const Stackup& stackup, const NamedConstant& impedance) {
    const int ohms = static_cast<int>(impedance.value);
    const std::string key = "pair_" + std::to_string(ohms) + "_ohm_mm", title = std::to_string(ohms) + " ohm pair width/gap mm";
    const DifferentialGeometry* pair = stackup.pair(ohms);
    if (!pair) return {key, title, "not in catalogue", nothing()};
    return {key, title, shown(pair->width_mm) + " / " + shown(pair->gap_mm),
            object({{"width", number(pair->width_mm)}, {"gap", number(pair->gap_mm)}, {"source", string(pair->source)}})};
}

std::optional<std::string> file_text(const std::filesystem::path& file) {
    if (!std::filesystem::exists(file)) return std::nullopt;
    std::ifstream in(file, std::ios::binary);
    if (!in) fail("cannot read " + file.string());
    std::ostringstream text;
    text << in.rdbuf();
    return text.str();
}

const JsonNode& field(const JsonNode& node, const std::string& key, JsonKind kind) {
    const JsonNode* found = object_field(node, key);
    if (!found || found->kind != kind) fail(std::string(verdict_report) + " field '" + key + "' is missing or has the wrong type");
    return *found;
}

}

std::vector<std::string> stackups_of(const RunConfig& config, const RunArguments& request) {
    std::vector<std::string> names = config.study_stackups;
    const auto given = request.options.find(stackups_option);
    if (given != request.options.end()) {
        names.clear();
        std::istringstream list(given->second);
        for (std::string name; std::getline(list, name, ',');) names.push_back(name);
        if (!given->second.empty() && given->second.back() == ',') names.emplace_back();
    }
    if (names.empty())
        fail(std::string("no stack-ups to compare; give ") + stackups_option + " NAME,NAME or set 'study.stackups' in " +
             run_config_file);
    std::set<std::string> seen;
    for (const std::string& name : names) {
        if (name.empty()) fail("a stack-up name is empty");
        if (!seen.insert(name).second) fail("stack-up '" + name + "' is listed twice");
    }
    return names;
}

RunConfig row_config(const RunConfig& config, const std::string& board, const std::string& stackup) {
    RunConfig row = config;
    row.stackup_of(board);
    row.stackup[board] = stackup;
    row.output = config.output / study_folder / stackup;
    return row;
}

std::filesystem::path table_file(const RunConfig& config, const std::string& board, const std::string& extension) {
    return config.output / study_folder / ("layers_" + board + extension);
}

std::vector<Cell> stackup_cells(const Stackup& stackup) {
    const double copper = static_cast<double>(stackup.copper.size()), signal = static_cast<double>(stackup.signal_layers());
    const std::string top = copper_role_name(stackup.reference_of(false).role), rear = copper_role_name(stackup.reference_of(true).role);
    std::string order;
    for (const CopperLayer& layer : stackup.copper) order += static_cast<char>(std::toupper(static_cast<unsigned char>(copper_role_name(layer.role)[0])));
    return {{"copper_layers", "copper layers", shown(copper), number(copper)},
            {"signal_layers", "signal layers", shown(signal), number(signal)},
            {"layer_order", "layer order", order, string(order)},
            {"thickness_mm", "thickness mm", shown(stackup.thickness_mm), number(stackup.thickness_mm)},
            {"outer_dielectric", "outer dielectric", stackup.prepreg, string(stackup.prepreg)},
            {"top_reference", "plane under top face", top, string(top)},
            {"rear_reference", "plane under rear face", rear, string(rear)},
            pair_cell(stackup, constants::lower_impedance),
            pair_cell(stackup, constants::upper_impedance)};
}

std::vector<Cell> layout_cells(const std::optional<std::string>& report) {
    std::vector<Cell> cells{{"size_before_mm", "size before squeeze mm", "not reported", nothing()},
                            {"size_mm", "size after squeeze mm", "not reported", nothing()},
                            {"area_mm2", "area after squeeze mm2", "not reported", nothing()},
                            {"parts_top", "parts on top", "not reported", nothing()},
                            {"parts_rear", "parts on rear", "not reported", nothing()}};
    if (!report) return cells;
    Words size(line_of(*report, "LAYOUT SQUEEZE: "), squeeze_report);
    size.expect("LAYOUT");
    size.expect("SQUEEZE:");
    const double width_before = size.number();
    size.expect("x");
    const double height_before = size.number();
    size.expect("mm");
    size.expect("to");
    const double width = size.number();
    size.expect("x");
    const double height = size.number();
    size.expect("mm,");
    size.expect("area");
    size.number();
    size.expect("to");
    const double area = size.number();
    Words faces(line_of(*report, "FACES: "), squeeze_report);
    faces.expect("FACES:");
    faces.expect("top");
    faces.number();
    faces.expect("to");
    const double top = faces.number();
    faces.expect(",");
    faces.expect("rear");
    faces.number();
    faces.expect("to");
    const double rear = faces.number();
    auto cell = cells.begin();
    cell->text = size_text(width_before, height_before);
    cell->value = list({number(width_before), number(height_before)});
    ++cell;
    cell->text = size_text(width, height);
    cell->value = list({number(width), number(height)});
    ++cell;
    cell->text = shown(area);
    cell->value = number(area);
    ++cell;
    cell->text = shown(top);
    cell->value = number(top);
    ++cell;
    cell->text = shown(rear);
    cell->value = number(rear);
    return cells;
}

std::vector<Cell> gate_cells(const std::optional<JsonNode>& verdict, int status, std::vector<std::string>& notes) {
    if (!verdict) {
        notes.push_back("the build ended with status " + std::to_string(status) + " before it reported its gates");
        return {{"gates", "gates passed", "not reported", nothing()}, {"result", "result", "ERROR", string("ERROR")}};
    }
    std::size_t passed = 0;
    const auto& gates = field(*verdict, "gates", JsonKind::Object).object_value;
    for (const auto& [name, gate] : gates) {
        const std::string& state = field(gate, "status", JsonKind::String).string_value;
        if (state == "PASS") ++passed;
        else if (state != "SKIP")
            notes.push_back(name + " " + state + (field(gate, "mandatory", JsonKind::Bool).bool_value ? "" : " (advisory)"));
    }
    const std::string result = field(*verdict, "board_ok", JsonKind::Bool).bool_value ? "PASS" : "FAIL";
    const double count = static_cast<double>(passed), total = static_cast<double>(gates.size());
    return {{"gates", "gates passed", shown(count) + " of " + shown(total), object({{"passed", number(count)}, {"total", number(total)}})},
            {"result", "result", result, string(result)}};
}

Row measured_row(const Stackup& stackup, const std::filesystem::path& output, int status) {
    Row row;
    row.stackup = stackup.fabricator_name;
    row.output = output;
    row.cells = stackup_cells(stackup);
    const std::filesystem::path reports = output / reports_folder;
    const std::optional<std::string> verdict = file_text(reports / verdict_report);
    std::optional<JsonNode> gates;
    if (verdict) gates = parse_json_text(*verdict, (reports / verdict_report).string());
    for (auto& cells : {layout_cells(file_text(reports / squeeze_report)), gate_cells(gates, status, row.notes)})
        row.cells.insert(row.cells.end(), cells.begin(), cells.end());
    return row;
}

std::string table(const std::string& board, const std::vector<Row>& rows) {
    if (rows.empty()) fail("no stack-up was studied");
    const std::string gap(2, ' ');
    std::size_t lead = 0;
    for (const Cell& cell : rows.front().cells) lead = std::max(lead, cell.title.size());
    const auto padded = [](const std::string& text, std::size_t width) { return text + std::string(width - text.size(), ' '); };
    std::vector<std::size_t> widths;
    for (const Row& row : rows) {
        if (row.cells.size() != rows.front().cells.size()) throw std::logic_error("study rows differ in their columns");
        std::size_t width = row.stackup.size();
        for (const Cell& cell : row.cells) width = std::max(width, cell.text.size());
        widths.push_back(width);
    }
    const auto ended = [](std::string line) { return line.erase(line.find_last_not_of(' ') + 1) + "\n"; };
    std::string out = "LAYER STUDY: " + board + "\n", head = padded("stack-up", lead);
    for (std::size_t index = 0; index < rows.size(); ++index) head += gap + padded(rows[index].stackup, widths[index]);
    out += ended(head);
    for (std::size_t line = 0; line < rows.front().cells.size(); ++line) {
        std::string text = padded(rows.front().cells[line].title, lead);
        for (std::size_t index = 0; index < rows.size(); ++index) {
            if (rows[index].cells[line].key != rows.front().cells[line].key) throw std::logic_error("study rows differ in their columns");
            text += gap + padded(rows[index].cells[line].text, widths[index]);
        }
        out += ended(text);
    }
    out += "gates not passed:\n";
    for (const Row& row : rows) {
        std::string notes;
        for (const std::string& note : row.notes) notes += (notes.empty() ? "" : "; ") + note;
        out += gap + row.stackup + ": " + (notes.empty() ? "none" : notes) + "\n";
    }
    out += "outputs:\n";
    for (const Row& row : rows) out += gap + row.stackup + ": " + row.output.generic_string() + "\n";
    return out;
}

std::string document(const std::string& board, const std::vector<Row>& rows) {
    std::vector<JsonNode> entries;
    for (const Row& row : rows) {
        std::vector<std::pair<std::string, JsonNode>> fields{{"stackup", string(row.stackup)}, {"output", string(row.output.generic_string())}};
        for (const Cell& cell : row.cells) fields.emplace_back(cell.key, cell.value);
        std::vector<JsonNode> notes;
        for (const std::string& note : row.notes) notes.push_back(string(note));
        fields.emplace_back("not_passed", list(std::move(notes)));
        entries.push_back(object(std::move(fields)));
    }
    return written(object({{"schema", string(table_schema)}, {"board", string(board)}, {"rows", list(std::move(entries))}}), "") + "\n";
}

}
