#pragma once

#include "schgen/schematic_place.hpp"
#include "schgen/quantize.hpp"

#include <algorithm>
#include <array>
#include <map>
#include <memory>
#include <optional>
#include <tuple>

namespace schgen::schematic_place {

inline constexpr double U = symbol_grid;
inline constexpr double NC_MARKER = 1.27;
inline constexpr RoutePoint A4_CENTER{148.59, 100.33}, A3_CENTER{210.82, 148.59};
inline constexpr double A3_TITLEBLOCK_LEFT = 300.0, A3_TITLEBLOCK_TOP = 252.9;
inline constexpr double TITLEBLOCK_MARGIN = 4.0, PAPER_H_BUDGET = 240.0, PAPER_W_BUDGET = 330.0;
inline constexpr double CHAR_W = 0.95, TEXT_SIZE = 1.27, LINE_H = 1.6;
inline constexpr double GLABEL_PAD_LEN = 2.0, GLABEL_H = 2.2, GLABEL_INSET = 0.254;
inline double gsnap(double v) { return schgen::gsnap(v, U); }
inline double gfloor(double v) { return schgen::gfloor(v, U); }
inline double gceil(double v) { return schgen::gceil(v, U); }

// Python dictionaries iterate in insertion order, including after erasing and
// reinserting a key. References/iterators invalidate on insertion or erasure;
// shared Trunk/FloatChain payloads preserve the shallow aliases Python uses.
template <typename T> class OrderedMap {
public:
    using Entries = std::vector<std::pair<std::string, T>>;
    auto begin() { return entries_.begin(); }
    auto end() { return entries_.end(); }
    auto begin() const { return entries_.begin(); }
    auto end() const { return entries_.end(); }
    auto find(const std::string& key) {
        return std::find_if(begin(), end(), [&](const auto& item) { return item.first == key; });
    }
    auto find(const std::string& key) const {
        return std::find_if(begin(), end(), [&](const auto& item) { return item.first == key; });
    }
    bool contains(const std::string& key) const { return find(key) != end(); }
    T& operator[](const std::string& key) {
        const auto it = find(key);
        if (it != end()) return it->second;
        entries_.emplace_back(key, T{});
        return entries_.back().second;
    }
    T& at(const std::string& key) {
        const auto it = find(key);
        if (it == end()) throw SchematicPlaceError("missing placement key: " + key);
        return it->second;
    }
    const T& at(const std::string& key) const {
        const auto it = find(key);
        if (it == end()) throw SchematicPlaceError("missing placement key: " + key);
        return it->second;
    }
    bool erase(const std::string& key) {
        const auto it = find(key);
        if (it == end()) return false;
        entries_.erase(it);
        return true;
    }
    bool empty() const { return entries_.empty(); }
    std::size_t size() const { return entries_.size(); }
    void clear() { entries_.clear(); }
private:
    Entries entries_;
};

using Point = RoutePoint;
using Refs = std::vector<std::string>;
using RefMap = OrderedMap<Refs>;
using PinKey = std::pair<std::string, std::string>;
using Handled = std::set<std::tuple<std::string, std::string, std::string>>;
struct Leg { std::string ref, a, b; };
struct FloatLeg { std::string ref, far, kind; };
using FloatLegs = OrderedMap<std::vector<FloatLeg>>;
struct ChainEnd { std::string ref, net, far, kind; };
struct Line {
    std::string net;
    Point pin_pt;
    std::optional<std::string> attach;
    std::optional<std::pair<std::string, std::string>> attach_div;
    std::string net_class = "port", pin_etype;
    bool force_label = false;
};
struct FloatChain {
    std::string kind, root;
    std::vector<Leg> legs;
    RefMap hangs;
};
using ChainPtr = std::shared_ptr<FloatChain>;
struct TrunkDirect { Point pin_pt; std::string side; };
struct TrunkRung {
    std::string net;
    Point pin_pt;
    std::string kind;
    Refs legs;
    double row = 0.0;
};
struct Trunk {
    std::string net, zone = "below";
    std::vector<TrunkDirect> direct;
    std::vector<TrunkRung> rungs;
    Refs terms;
    std::vector<ChainPtr> chains;
    std::vector<double> nodes;
    double y = 0.0;
};
using TrunkMap = OrderedMap<std::shared_ptr<Trunk>>;
struct Stage { std::string kind, out, sw, inductor; };
using StageMap = OrderedMap<Stage>;
struct PinAt { const SymbolPin* pin; Point point; };
struct RailPin { const SymbolPin* pin; Point point; const CircuitNetIr* net; };
using PinPositions = OrderedMap<Point>;
struct PlacedBody {
    std::size_t part_index;  // Stable across vector reallocations, unlike a reference.
    const SymbolDef* symbol;
    VisualBox body;
    OrderedMap<std::vector<PinAt>> sides;
};
struct SideTip { std::string ref, number, side; Point point; };
struct TipGroup { Point first; std::vector<Point> rest; };
struct FacingPair { std::string net; Point a, b; std::vector<Point> a_extra, b_extra; };
struct ChainScore { std::array<int, 3> score; OrderedMap<int> orient; };
struct RungIslet { std::string trunk_net, far_net, ref; };

VisualBox body_box_page(const SymbolDef&, double ax, double ay, int rotation,
                        const std::string& kind, const std::string& owner);
Point value_anchor(const SymbolDef&, double ax, double ay, int rotation);
std::vector<VisualBox> pin_text_boxes(const SymbolDef&, const SchematicPlacedPart&);
const SymbolPin& pin(const SymbolDef&, const std::string& number);
std::string side_of_rotation(int rotation);
std::pair<double, double> text_wh(const std::string& text);
Box4 centered_box(const std::string& text, double x, double y, bool vertical = false);
Box4 glabel_box(const std::string& text, double x, double y, int rotation);
Box4 llabel_box(const std::string& text, double x, double y, int rotation = 0);

class Engine {
public:
    // Own an immutable circuit snapshot; SymbolLibrary must outlive this Engine
    // and must not be cleared while future template methods retain symbol pins.
    // Input is the core circuit AFTER probes/mounting holes have been split.
    Engine(const CircuitSheetIr&, SymbolLibrary&, const SchematicSpacing& = {});
    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;
    const CircuitSheetIr c;
    SymbolLibrary& lib;
    SchematicSpacing sp;
    SchematicPlacement pl;
    std::size_t _pwr = 0, _flg = 0, _n_box_bucks = 0;
    std::set<std::string> _done, _pin_islets, _comp_starts;
    std::vector<RungIslet> _rung_islets;
    std::vector<double> _sig_rows;
    std::map<double, std::string> _rail_row_net;
    std::vector<std::pair<std::size_t, VisualBox>> _deferred_texts;
    OrderedMap<int> orient;
    Refs multi, shunts;
    std::set<std::string> multi_nets;
    RefMap cluster, hang;
    OrderedMap<std::vector<std::pair<std::string, std::string>>> pull;
    std::vector<Leg> series;
    TrunkMap trunks;
    std::vector<ChainPtr> float_chains;

    // Implemented by schematic_place_core.cpp (place.py through line 779).
    const CircuitPartIr& part(const std::string& ref) const;
    const CircuitNetIr& net(const std::string& name) const;
    const CircuitNetIr* net_of(const std::string& ref, const std::string& number) const;
    std::string other_pin(const std::string& ref, const std::string& number);
    std::string _pin_of_net(const std::string& ref, const std::string& net);
    std::string _power_lib(const std::string& net) const;
    // Return stable indices rather than references invalidated by later appends.
    std::size_t power(const std::string& net, double x, double y, int rotation = 0,
                       bool show_value = true);
    std::size_t flag(const std::string& net, double x, double y, int rotation);
    void passive(const std::string& ref, double x, double y, int rotation,
                 const std::string& text_side = "right");
    void label(const std::string& net, double x, double y, int rotation,
               const std::string& shape = "bidirectional");
    void llabel(const std::string& net, double x, double y, int rotation = 0);
    Point _dodge_value_off_nc(const std::string& text, Point value, double ax, double ay) const;
    std::vector<Box4> _plan_seg_boxes() const;
    std::vector<Box4> _nc_boxes() const;
    std::vector<Box4> _boxes() const;
    bool _spot_free(const Box4&, double pad = 0.25) const;
    Box4 _extent() const;
    double _band_edge(double y0, double y1, int side, double default_edge) const;
    void _classify();
    void _extract_float_chains();
    ChainPtr _linearise(const std::set<std::string>& component, const FloatLegs& legs);
    ChainPtr _linearise_port_strap(const std::set<std::string>& component,
                                  const FloatLegs& legs, const std::vector<ChainEnd>& ends);

    // FUTURE implementation seams, declared only. No placeholder bodies. Further
    // private helpers can be added by each slice without changing the public API.
    // schematic_place_fanout.cpp: two-pin seating, body/text, fanout and trunks.
    std::pair<Point, std::string> _vertical_2pin(const std::string&, double x, double y,
        const std::string& attach_net, bool downward, const std::string& text_side = "right");
    void _horizontal_2pin(const std::string&, double x, double y,
        const std::string& left_net, const std::string& text_side = "right");
    PlacedBody _place_body(const std::string&, double ax, double ay);
    void _part_texts(std::size_t placed_part, const VisualBox&);
    void _fan_side(const std::string&, const std::string& side, const std::vector<PinAt>&, Handled&);
    void _fan_rail_run(const std::vector<RailPin>&, int sign, const std::vector<Point>& rows);
    void _fan_rail_comb(const std::string&, const std::vector<Point>&, int sign,
                        std::size_t box_mark, const OrderedMap<std::size_t>& plan_marks);
    bool _foreign_rows_clear(const Box4&, const std::string&, const std::set<double>& own_ys) const;
    std::pair<double, Box4> _series_inline(const Leg&, const std::string&, Point tap, int sign,
                                          std::optional<Box4> avoid = std::nullopt);
    double _attach_halfw(const Line&);
    std::pair<double, double> _attach_band(const Line&);
    double _attach_column(const Line&, Point tap, double rank_y, bool downward);
    double _divider(const Line&, Point tap);
    void _cell(const std::string&, double ax, double ay, Handled&, TrunkMap&,
               bool defer_texts = false, int drop_dir = -1);
    std::shared_ptr<Trunk> _rung_of(const std::string&, const TrunkMap&) const;
    void _build_trunk(Trunk&);
    void _bottom_port_drop(const std::string&, const SymbolPin&, Point, double row, int direction);
    double _rung_bar_y(const Trunk&) const;
    std::vector<double> _ladder_rung(Trunk&, const std::string&, Point, Refs legs, double bar);
    std::vector<double> _side_ladder_rung(Trunk&, const std::string&, Point, int sign, Refs legs, double ty);
    double _free_drop_col(int sign, double start, double attach_y, double ty,
                          const std::string& ref, const std::string& net, const std::string& text_side);
    double _lane_x(int sign, double y0, double y1, double start) const;
    std::vector<std::pair<Point, Point>> _escape_run_legs(const std::string&, double px, double py, double tx);
    std::vector<Seg2> _plan_raw_segs(const std::set<std::string>& skip) const;
    std::vector<Seg2> _stem_segs(const std::set<std::string>& skip);
    bool _corridor_free(double y, double xa, double xb, const std::set<std::string>& skip);
    bool _vband_stem_free(double x, double y0, double y1, const std::set<std::string>& skip);
    std::optional<double> _lane_in_dir(int sign, Point, double ty, const std::string&);
    bool _corridor_clear_vert(double x, double pin_y, double ty, const std::string&) const;
    double _escape_lane(int sign, Point, double ty, const std::string&);
    bool _cell_free(double x, double y, const std::string&);
    std::vector<Point> _escape_path(int sign, Point, double ty, const std::string&);
    std::vector<Point> _bfs_escape(Point, double ty, const std::string&);
    void _collect_trunk_pins(const std::string&, double ax, double ay, TrunkMap&, const Handled&);
    bool _net_shared(const std::string& net, const std::string& ref) const;
    std::optional<Leg> _series_of(const std::string& net) const;
    std::optional<FloatChain> _local_drop_chain(const std::string& net, const std::string& ref);
    void _stack_from_pin(const FloatChain&, Point, const std::string& side,
                          const std::string& text_side = "right");
    void _signal_islet_drop(const std::string&, Point, const std::string& side);
    void _chain_mid_features(const FloatChain&, const std::string&, Point);
    void _chain_mid_features_left(const FloatChain&, const std::string&, Point);
    void _bridge(const std::string& net);
    int _power_rot(const std::string&, bool downward) const;
    int _rail_rot(const std::string&, const std::string& side) const;
    void _rail_stub(const std::string&, Point, const std::string& side);
    void _rail_bus(const std::string&, const std::vector<Point>&, const std::string& side);
    double _cell_floor(double x0, double x1) const;

    // schematic_place_templates.cpp: connector/regulator and decoupling columns.
    static constexpr double CONN_RUN = 10.16, CONN_COL_GAP = 1.27, CONN_MID_GAP = 2.54;
    static constexpr double CONN_STRIP_STUB = 2.54, CONN_STRIP_BAR = 2.54;
    static constexpr double CONN_EXT = 2.54, CONN_ROW = 2.54;
    SchematicPlacement _connector_template(const std::string&);
    StageMap _detect_stages();
    std::optional<Stage> _detect_buck_topology(const std::string&, const SymbolDef&);
    SchematicPlacement _regulator_template(StageMap stages);
    void _stage_row(const std::string&, const Stage&, double ay, RefMap& in_caps, RefMap& out_caps);
    void _buck_box_stage(const std::string&, const Stage&, double ay, RefMap&, RefMap&);
    void _buck_right(const std::string&, const Stage&, double ay, const PinPositions&,
                     const SymbolDef&, RefMap& out_caps);
    void _ldo_right(const std::string&, const Stage&, double ay, const PinPositions&,
                    const SymbolDef&, RefMap& out_caps);
    std::optional<std::string> _stage_in_rail(const std::string&);
    bool _is_fb_pin(const SymbolPin&, const std::string& net, const std::string& out_rail) const;
    std::optional<std::string> _stage_fb_net(const std::string&, const Stage&);
    bool _stage_has_left_input(const std::string&);
    std::string _stage_in_rail_box(const std::string&);
    std::optional<std::string> _stages_out(const std::string&);
    void _box_right_pin_islet(const std::string&, Point);
    void _box_left_pin_islet(const std::string&, Point, const VisualBox&);
    void _fb_left_network(const std::string&, const Stage&, Point,
                          const std::string& fb_net, const std::string& out_rail);
    bool _needs_flag(const std::string&);
    double _farm_row_right_bound(double ex0, double ex1_flow) const;
    void _decoupling_cluster(double ax, double ay, const VisualBox&);
    void _cluster_cap(const std::string&, double x, double cy);
    void _flags_row();
    void _power_at(const std::string&, double x, double y, int rotation, std::optional<Point> value);
    static double _glabel_len(const std::string&);

    // schematic_place_chain.cpp: component ordering, channel layout, leftovers.
    SchematicPlacement _stack_columns_template();
    SchematicPlacement _chain_template();
    Refs _chain_order();
    ChainScore _eval_chain(const Refs&);
    static std::optional<TipGroup> _tip_group(std::vector<Point>);
    std::vector<FacingPair> _facing_pairs(const std::string&, const std::string&);
    std::vector<SideTip> _side_tips(const std::string&);
    bool _on_net(const std::string& ref, const std::string& pin, const std::string& net) const;
    std::string _pin_num_at(const std::string&, Point, const std::string& side);
    double _side_reach(const std::string&, const std::string& side,
                       const TrunkMap* jobs = nullptr, const std::set<std::string>& exclude = {});
    void _rail_decoupling_columns();
    void _leftover_chains_columns();
    void _port_strap_columns();
    void _shunt_cells(Handled&);
    void _pull_rank_columns();
    void _series_port_columns();
    void _trunk_series_columns();
    void _rung_islet_columns();
    void _rung_islet_drop(const std::string&, Point, int sign);
    void _pin_divider_columns();
    SchematicPlacement run();

private:
    std::map<std::string, std::size_t> parts_, nets_;
    std::map<PinKey, std::size_t> pin2net_;
};

// schematic_place_pages.cpp: auxiliary split/add, centering, visual retries and
// partitioning. These future definitions implement the public entry points.
std::pair<CircuitSheetIr, Refs> split_auxiliary(const CircuitSheetIr&);
void add_probe_row(Engine&, const CircuitSheetIr& original, const Refs&);
void translate(SchematicPlacement&, double dx, double dy);
void center_on_sheet(SchematicPlacement&);
std::vector<std::set<std::string>> signal_blobs(const CircuitSheetIr&, SymbolLibrary&);
std::vector<CircuitSheetIr> partition_pages(const CircuitSheetIr&, SymbolLibrary&);

}  // namespace schgen::schematic_place
