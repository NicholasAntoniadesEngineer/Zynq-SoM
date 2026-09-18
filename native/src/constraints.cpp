#include "schgen/constraints.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/atomic_file.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <map>
#include <set>
#include <sstream>
#include <tuple>

namespace schgen {
namespace {
const JsonNode& get(const JsonNode& n, const std::string& key, JsonKind kind) {
    const auto* p = object_field(n, key);
    if (!p || p->kind != kind) throw ProjectError("SI specification requires " + key + " with the correct type");
    return *p;
}
std::string optional_text(const JsonNode& n, const std::string& key) {
    return object_field(n, key) ? get(n, key, JsonKind::String).string_value : "";
}
std::string general(double value) {
    if (!std::isfinite(value)) throw ProjectError("non-finite layout constraint");
    std::ostringstream stream;
    stream.imbue(std::locale::classic()); stream << std::setprecision(6) << value;
    return stream.str();
}
std::string quote_csv(const std::string& value) {
    if (value.find_first_of(",\"\r\n") == std::string::npos) return value;
    std::string result = "\"";
    for (char c : value) { if (c == '"') result += '"'; result += c; }
    return result + '"';
}
std::string join(const std::vector<std::string>& items, const std::string& separator) {
    std::string result;
    for (const auto& item : items) { if (!result.empty()) result += separator; result += item; }
    return result;
}
}
double PairSignalSpec::match_tol_mm() const { return py_round(match_tol_mil * 0.0254, 4); }
double PairSignalSpec::intra_pair_skew_mm() const { return py_round(intra_pair_skew_mil * 0.0254, 4); }
std::vector<PairSignalSpec> parse_signal_specs(const JsonNode& data) {
    if (data.kind != JsonKind::Object) throw ProjectError("SI specification must be an object");
    const auto* pairs = object_field(data, "pairs");
    if (!pairs) return {};
    if (pairs->kind != JsonKind::Array) throw ProjectError("SI pairs must be an array");
    std::vector<PairSignalSpec> result;
    for (const auto& p : pairs->array_value) {
        PairSignalSpec spec;
        spec.interface = get(p,"interface",JsonKind::String).string_value;
        spec.signal = optional_text(p,"signal");
        spec.net_p = get(p,"net_p",JsonKind::String).string_value;
        spec.net_n = get(p,"net_n",JsonKind::String).string_value;
        const double impedance = get(p,"z_diff_ohm",JsonKind::Number).number_value;
        if (!std::isfinite(impedance) || impedance < std::numeric_limits<int>::min() || impedance > std::numeric_limits<int>::max())
            throw ProjectError("SI impedance out of range");
        spec.z_diff_ohm = static_cast<int>(impedance);
        spec.match_tol_mil = get(p,"match_tol_mil",JsonKind::Number).number_value;
        spec.intra_pair_skew_mil = get(p,"intra_pair_skew_mil",JsonKind::Number).number_value;
        if (!std::isfinite(spec.match_tol_mil) || !std::isfinite(spec.intra_pair_skew_mil)) throw ProjectError("non-finite SI target");
        spec.ac_coupled = get(p,"ac_coupled",JsonKind::Bool).bool_value;
        spec.spec_cite = get(p,"spec_cite",JsonKind::String).string_value;
        spec.notes = optional_text(p,"notes");
        result.push_back(std::move(spec));
    }
    std::stable_sort(result.begin(),result.end(),[](const auto& a,const auto& b){
        return std::tie(a.interface,a.net_p) < std::tie(b.interface,b.net_p);
    });
    return result;
}
std::vector<PairSignalSpec> load_signal_specs(const std::filesystem::path& path) {
    return parse_signal_specs(parse_json_file(path.string()));
}
const DifferentialGeometry* differential_geometry(int impedance) {
    static const DifferentialGeometry usb{90,0.2611,0.2032,"JLCPCB calculator, JLC04161H-7628 outer/L2"};
    static const DifferentialGeometry tmds{100,0.2052,0.2032,"JLCPCB calculator, JLC04161H-7628 outer/L2"};
    return impedance == 90 ? &usb : impedance == 100 ? &tmds : nullptr;
}
std::string port_net_class(const CircuitPortIr& p) {
    if (p.kind == "usb_hs_pair") return "DP90_USB";
    if (p.kind == "tmds_pair") return "DP100_TMDS";
    if (p.kind == "diff_pair") return "DP" + (p.has_impedance ? std::to_string(p.impedance) : "None") + "_DIFF";
    if (p.kind == "i2c") return "I2C";
    if (p.kind == "sd_bus") {
        if (!p.has_level_v) throw ProjectError("SD bus needs a voltage level");
        auto level = general(p.level_v); std::replace(level.begin(),level.end(),'.','V');
        return "SD_" + level;
    }
    return "Default";
}
bool needs_signal_specs(const std::vector<ProjectCircuit>& sheets) {
    for (const auto& sheet : sheets) for (const auto& net : sheet.circuit.nets)
        if (net.net_class == "port" && !circuit_port_type(sheet.circuit,net.name).pair_with.empty()) return true;
    return false;
}
LayoutConstraints generate_layout_constraints(const std::vector<ProjectCircuit>& sheets,
        const std::vector<PairSignalSpec>& specs, const std::string& source) {
    std::map<std::string,const PairSignalSpec*> by_net;
    for (const auto& spec : specs) { by_net[spec.net_p] = &spec; by_net[spec.net_n] = &spec; }
    std::map<std::string,const DifferentialGeometry*> classes;
    std::vector<std::vector<std::string>> rows;
    for (const auto& sheet : sheets) for (const auto& net : sheet.circuit.nets) {
        if (net.net_class != "port") continue;
        const auto p = circuit_port_type(sheet.circuit,net.name);
        const auto cls = port_net_class(p);
        const auto* geometry = p.has_impedance ? differential_geometry(p.impedance) : nullptr;
        classes.emplace(cls,geometry);
        std::string group,tolerance,skew_cite;
        if (!p.pair_with.empty()) {
            const auto found = by_net.find(net.name);
            if (found == by_net.end()) throw ProjectError(net.name + ": typed " + p.kind + " but has no row in " + source +
                " — every pair's intra-pair skew is read per net from the researched table; there is no per-kind default to fall back to. Add the pair with its standard citation.");
            std::set<std::string> pair{net.name,p.pair_with};
            group = "PAIR:" + join(std::vector<std::string>(pair.begin(),pair.end()),"/");
            tolerance = general(found->second->intra_pair_skew_mm());
            skew_cite = "skew: " + found->second->spec_cite;
        } else if (p.kind == "sd_bus") { group = "BUS:" + (p.bus.empty() ? "SD" : p.bus); tolerance = "2.5"; }
        std::vector<std::string> notes;
        if (!p.bus.empty()) notes.push_back("bus="+p.bus);
        if (p.has_speed_hz && p.speed_hz) notes.push_back("speed="+std::to_string(p.speed_hz)+"Hz");
        if (p.has_level_v) notes.push_back("level="+general(p.level_v)+"V");
        if (!p.expect.empty()) notes.push_back("deferred: "+p.expect);
        if (geometry) notes.push_back(geometry->source);
        if (!skew_cite.empty()) notes.push_back(skew_cite);
        rows.push_back({net.name,sheet.name,p.kind,cls,p.has_impedance && p.impedance ? std::to_string(p.impedance) : "",
            geometry ? general(geometry->width_mm) : "",geometry ? general(geometry->gap_mm) : "",p.pair_with,
            group,tolerance,join(notes,"; ")});
    }
    std::stable_sort(rows.begin(),rows.end(),[](const auto& a,const auto& b){
        return std::tie(a[3],a[1],a[0]) < std::tie(b[3],b[1],b[0]);
    });
    LayoutConstraints result; result.port_count = rows.size();
    result.csv = "net,sheet,kind,net_class,impedance_ohm,track_width_mm,pair_gap_mm,pair_with,length_match_group,match_tolerance_mm,notes\r\n";
    for (const auto& row : rows) {
        for (std::size_t i = 0; i < row.size(); ++i) { if (i) result.csv += ','; result.csv += quote_csv(row[i]); }
        result.csv += "\r\n";
    }
    result.dru = "(version 1)\n\n# Generated by schgen/constraints.py from typed ports.\n"
        "# Stackup: JLCPCB JLC04161H-7628 (4L 1.6mm, 7628 prepreg 0.2104mm).\n"
        "# Geometry source: JLCPCB impedance calculator for this stackup\n"
        "# (90R diff: 0.2611/0.2032mm; 100R diff: 0.2052/0.2032mm, outer vs L2).\n"
        "# Assign nets to the classes listed in layout_constraints.csv first.\n";
    for (const auto& [name,geo] : classes) {
        if (!geo) continue;
        const auto width = general(geo->width_mm), gap = general(geo->gap_mm);
        result.dru += "\n(rule \"" + name + "_geometry\"\n  (condition \"A.NetClass == '" + name + "'\")\n"
            "  (constraint track_width (min " + width + "mm) (opt " + width + "mm) (max " + width + "mm))\n"
            "  (constraint diff_pair_gap (min " + gap + "mm) (opt " + gap + "mm))\n)\n";
    }
    return result;
}
LayoutConstraints write_layout_constraints(const std::vector<ProjectCircuit>& sheets,
        const std::filesystem::path& specification, const std::filesystem::path& directory) {
    const auto specs = needs_signal_specs(sheets) ? load_signal_specs(specification) : std::vector<PairSignalSpec>{};
    auto result = generate_layout_constraints(sheets,specs,specification.string());
    write_atomic_file((directory/"layout_constraints.kicad_dru").string(),{result.dru.begin(),result.dru.end()});
    write_atomic_file((directory/"layout_constraints.csv").string(),{result.csv.begin(),result.csv.end()});
    return result;
}
}  // namespace schgen
