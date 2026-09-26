#pragma once
#include "schgen/ratsnest_documents.hpp"
#include "pcb_checks_internal.hpp"
#include <set>

namespace schgen::ratsnest_detail {
using namespace pcb_checks;
using Rgba = std::array<unsigned char, 4>;
inline constexpr Rgba background{15,17,21,255};
inline constexpr Rgba outline{15,17,21,255};
void validate(const PcbModel&, const RatsnestNets&, const RatsnestEdges&);
void safe_sheet(const std::string&);
int raster_size(double);
struct Raster {
    int width, height;
    std::string pixels;
    Raster(double width, double height);
    void pixel(int x, int y, Rgba);
    void hline(int x0, int y, int x1, Rgba);
    void rectangle(Box4, const std::optional<Rgba>& fill, Rgba edge, int thick);
    void line(double x0, double y0, double x1, double y1, Rgba, int width);
    void text(double x, double y, const std::string&, Rgba);
    std::string png() const;
};
inline RatsnestColor color(const RatsnestPalette& p, const std::string& name) {
    auto it=p.find(name);return it==p.end()?RatsnestColor{140,140,140}:it->second;
}
inline Rgba rgba(RatsnestColor c,unsigned char alpha){return {c[0],c[1],c[2],alpha};}
inline RatsnestImage image(const std::string& filename,const Raster& im){return {filename,im.png(),im.width,im.height};}
} // namespace schgen::ratsnest_detail
