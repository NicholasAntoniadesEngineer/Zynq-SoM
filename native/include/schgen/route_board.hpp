#pragma once

#include "schgen/named_constant.hpp"
#include "schgen/route_geometry.hpp"

#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace schgen::route {

namespace constants {
inline constexpr NamedConstant layer_limit{"layer_limit", 12, "layers", "policy",
    "most copper layers a board may state; user ruling 2026-11-27 (any count from 1 to 12)"};
inline constexpr NamedConstant index_cell{"index_cell", 2e6, "nm", "policy",
    "side of one cell of the copper index; a few track pitches, so a query touches few cells and a cell holds few items"};
inline constexpr std::array route_board_registry{layer_limit, index_cell};
}

inline constexpr int no_net = -1;

class RouteError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

enum class LayerKind : std::uint8_t { signal, plane };

struct Layer {
    std::string name;
    LayerKind kind = LayerKind::signal;
    int plane_net = no_net;
};

struct ViaKind {
    std::string name;
    Nm pad = 0, drill = 0;
    std::size_t first = 0, last = 0;
};

struct NetClass {
    std::string name;
    Nm track = 0, clearance = 0;
    std::size_t via = 0;
};

struct Rules {
    std::vector<Layer> layers;
    std::vector<NetClass> classes;
    std::vector<ViaKind> vias;
    Nm edge_clearance = 0, hole_clearance = 0, hole_spacing = 0;
    Nm clearance(std::size_t first, std::size_t second) const;
    void validate() const;
};

struct Net {
    std::string name;
    std::size_t net_class = 0;
};

enum class ItemKind : std::uint8_t { pad, track, via, keepout };

struct Item {
    ItemKind kind = ItemKind::track;
    int net = no_net;
    std::size_t first = 0, last = 0;
    Shape shape;
    Nm drill = 0;
    std::string owner;
};

struct Board {
    Box outline;
    Rules rules;
    std::vector<Net> nets;
    std::vector<Item> fixed;
    void validate() const;
};

Item track(const Board& board, int net, std::size_t layer, Point from, Point to);
Item via(const Board& board, int net, Point at);
const char* kind_name(ItemKind kind);

struct Conflict {
    std::size_t item = 0;
    bool edge = false;
};

class World {
public:
    explicit World(const Board& board);
    const Board& board() const { return board_; }
    std::size_t size() const { return items_.size(); }
    const Item& item(std::size_t id) const { return items_[id]; }
    bool present(std::size_t id) const { return live_[id] != 0; }
    std::optional<Conflict> conflict(const Item& candidate) const;
    std::vector<std::size_t> conflicts(const Item& candidate) const;
    std::size_t add(const Item& item);
    void remove(std::size_t id);
    std::size_t mark() const { return journal_.size(); }
    void rollback(std::size_t mark);
    std::vector<Item> routed() const;

private:
    using Key = std::uint64_t;
    static Key key(std::size_t layer, Nm column, Nm row);
    template <typename Visit> void each_cell(const Item& item, const Visit& visit) const;
    bool clash(const Item& candidate, const Item& other) const;
    void index(std::size_t id, bool insert);

    const Board& board_;
    std::vector<Item> items_;
    std::vector<char> live_;
    std::size_t fixed_ = 0;
    std::unordered_map<Key, std::vector<std::size_t>> cells_;
    std::vector<std::pair<std::size_t, bool>> journal_;
    Nm reach_ = 0;
};

}
