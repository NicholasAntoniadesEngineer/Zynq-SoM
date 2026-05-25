"""Regenerate ``carrier_template.kicad_pro`` with hierarchical sheet paths."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectEmissionResult:
    project_path: Path
    root_uuid: str
    sheet_entries: tuple[dict[str, str], ...]


def emit_project_file(
    project_path: Path,
    root_schematic_filename: str,
    root_uuid: str,
    block_names: tuple[str, ...],
) -> ProjectEmissionResult:
    """Write or update the KiCad project JSON for a hierarchical schematic tree."""
    if project_path.exists():
        project_data = json.loads(project_path.read_text(encoding="utf-8"))
    else:
        project_data = _default_project_skeleton()

    project_data["schematic"]["top_level_sheets"] = [
        {
            "filename": root_schematic_filename,
            "name": Path(root_schematic_filename).stem,
            "uuid": root_uuid,
        }
    ]

    sheet_entries: list[dict[str, str]] = []
    for block_name in block_names:
        sheet_entries.append(
            {
                "name": block_name,
                "filename": f"sheets/{block_name}.kicad_sch",
                "uuid": str(uuid.uuid4()),
            }
        )

    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(
        json.dumps(project_data, indent=2) + "\n",
        encoding="utf-8",
    )

    return ProjectEmissionResult(
        project_path=project_path,
        root_uuid=root_uuid,
        sheet_entries=tuple(sheet_entries),
    )


def _default_project_skeleton() -> dict:
    return {
        "board": {
            "design_settings": {
                "defaults": {
                    "board_outline_line_width": 0.05,
                    "copper_line_width": 0.2,
                }
            }
        },
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        "libraries": {
            "pinned_footprint_libs": [],
            "pinned_symbol_libs": [],
        },
        "meta": {"filename": "carrier_template.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [
                {
                    "bus_width": 12,
                    "clearance": 0.2,
                    "diff_pair_gap": 0.25,
                    "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.2,
                    "line_style": 0,
                    "microvia_diameter": 0.3,
                    "microvia_drill": 0.1,
                    "name": "Default",
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "priority": 2147483647,
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                    "track_width": 0.2,
                    "via_diameter": 0.6,
                    "via_drill": 0.3,
                    "wire_width": 0.1524,
                }
            ],
            "meta": {"version": 3},
            "netclass_assignments": [],
            "netclass_patterns": [],
        },
        "pcbnew": {"last_paths": {"gencad": "", "idf": "", "netlist": "", "plot": "", "pos_files": "", "specctra_dsn": "", "step": "", "svg": "", "vrml": ""}, "page_layout_descr_file": ""},
        "schematic": {
            "legacy_lib_dir": "",
            "legacy_lib_list": [],
            "meta": {"version": 1},
            "page_layout_descr_file": "",
            "plot_directory": "",
            "spice_current_sheet_as_root": False,
            "spice_external_command": "spice \"%I\"",
            "spice_model_current_sheet_as_root": True,
            "spice_save_all_currents": False,
            "spice_save_all_dissipations": False,
            "spice_save_all_voltages": False,
            "subpart_first_id": 65,
            "subpart_id_separator": 0,
            "top_level_sheets": [],
        },
        "sheets": [],
        "text_variables": {},
    }
