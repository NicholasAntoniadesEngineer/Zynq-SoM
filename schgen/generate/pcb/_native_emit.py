"""Transitional transport to the complete native PCB emitter."""
from dataclasses import asdict
from schgen.core import native, fallbacks
from schgen.core.quantize import STACK_THICKNESS_MM
from schgen.verify._native_pcb import snapshot
from . import constants as c


def prepare(model):
    raw, files = snapshot(model)
    raw.update(classes={k: asdict(v) if v is not None else None
                        for k, v in model.classes.items()},
               placed=model.placed, deferred=list(model.deferred),
               n_top=model.n_top, n_bottom=model.n_bottom, two_side=model.two_side,
               som_keepout=model.som_keepout, escape_meta=model.escape_meta or {},
               stage_moves=dict(model.stage_moves))
    return native.module().pcb_emission_prepare(raw, files)


def policy():
    return dict(
        header_descriptions=list(c._INT_DESC.items()),
        switch_descriptions=list(c._SW_DESC.items()),
        connector_descriptions=list(c._CONN_DESC.items()),
        connector_mating_faces=list(c.CONN_MATING_FACE.items()),
        footprint_aliases=list(c._FOOTPRINT_ALIASES.items()),
        isolation_prefixes=list(c.ISO_VOID_VALUES),
        ground_layer=c.GND_PLANE_LAYER, power_class=c.POWER_CLASS,
        gnd_plane_edge_back=c.GND_PLANE_EDGE_BACK,
        gnd_plane_clearance=c.GND_PLANE_CLEARANCE,
        pour_clearance=c.POUR_CLEARANCE, zone_min_thickness=c.ZONE_MIN_THICKNESS,
        isolation_margin=c.ISO_VOID_MARGIN,
        thermal_via_size=c.THERMAL_VIA_SIZE, thermal_via_drill=c.THERMAL_VIA_DRILL,
        thermal_via_clear=c.THERMAL_VIA_CLEAR, hole_samenet_pad=c.CLR_HOLE_SAMENET_PAD,
        thermal_via_h2h=c.THERMAL_VIA_H2H, thermal_via_edge=c.THERMAL_VIA_EDGE,
        thermal_via_spacing=c.THERMAL_VIA_SPACING,
        thermal_lattice_pitch=c.THERMAL_VIA_LATTICE_PITCH,
        default_track=c.DEFAULT_TRACK_MM, default_clearance=c.DEFAULT_CLEARANCE_MM,
        power_track=c.POWER_TRACK_MM, power_clearance=c.POWER_CLEARANCE_MM,
        minimum_hole_to_hole=c.MIN_HOLE_TO_HOLE, stack_thickness=STACK_THICKNESS_MM,
        thermal_copper=c.THERMAL_COPPER)


def write(model, path, kind, prepared=None):
    diagnostics, events = native.module().pcb_emission_write(
        prepare(model) if prepared is None else prepared, str(path), kind, policy())
    for line in diagnostics:
        print(line)
    for event in events:
        fallbacks.record(event)
