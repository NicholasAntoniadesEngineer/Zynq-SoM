# Subsystem file format (`schgen.subsystem/1`)

## 1. What a subsystem file is

A subsystem is a reusable circuit block (a camera port, a USB-C input, a regulator stage). Each one is the file `subsystems/<name>/subsystem.json` under the repository root. The application reads the file at run time, every time the subsystem is requested by name or the library is listed, so adding or editing a file needs no rebuild. The file is replayed through the `CircuitAuthor` API (`native/src/authoring.cpp`) by `author_subsystem_data` (`native/src/subsystem_authoring_data.cpp`). The folder name must equal the `name` field, and an unknown key at any level is an error.

Only a subfolder that contains a regular file named `subsystem.json` is loaded; other subfolders are ignored. A name that is also compiled in is an error (`subsystem NAME is defined twice: compiled in and by a file`).

Errors raised by the loader itself have the form `subsystem file <where>: <message>`. `<where>` is the file's `name` value, or `(unnamed)` if it has none. Three kinds of message do not carry that prefix: unknown keys (`unknown key 'K' in <where>`, where `<where>` is the name plus the entry, such as `<name> part R1`, `<name> port`, `<name> net`, `<name> hint`, `<name> draw`, `<name> waiver`, `<name> purpose`, `<name> free part`), messages from the JSON parser (which rejects a repeated key in one object: `duplicate key 'K'`), and messages from `CircuitAuthor`, which quote names with single quotes.

## 2. A complete small example

This file is `subsystems/i2c_esd/subsystem.json`. It uses every top-level key, both part forms, pin names (`U1.GND`, `U1.NC`), a `port` and a `pin` and a `net` purpose, and the three per-board forms. It was loaded through `author_subsystem_data` with and without board settings.

```json
{
  "schema": "schgen.subsystem/1",
  "name": "i2c_esd",
  "title": "ESD-protected I2C pair with pull-ups",
  "interface": ["+VDD", "GND", "SCL", "SDA"],
  "placement": {"region": "board", "silk_label": null, "far_guard_mm": null, "escape_basis": null, "escape_escalates": false, "reserves_edge": false},
  "checks": {"dividers": [], "divider_sources": [], "iset_window_ma": null},
  "parts": [
    {"ref": "U1", "part": "TPD4E02B04DQAR", "fields": {"NOTE": "ESD array"}},
    {
      "ref": "R1",
      "symbol": "Device:R",
      "value": "4k7",
      "footprint": "Resistor_SMD:R_0603_1608Metric",
      "fields": {"LCSC": "C23162"}
    },
    {
      "ref": "R2",
      "symbol": "Device:R",
      "value": "4k7",
      "footprint": "Resistor_SMD:R_0603_1608Metric",
      "fields": {"LCSC": "C23162"}
    }
  ],
  "nets": [
    {"name": "+VDD", "pins": ["R1.1", "R2.1"]},
    {"name": "GND", "pins": ["U1.GND"]},
    {"name": "SCL", "class": "port", "pins": ["R1.2", "U1.IO1"]},
    {"name": "SDA", "class": "port", "pins": ["R2.2", "U1.IO2"]}
  ],
  "unconnected": ["U1.IO3", "U1.IO4", "U1.NC"],
  "ports": [
    {
      "net": "SCL",
      "kind": "i2c",
      "role": "scl",
      "bus": {"instance": "i2c", "default": "SENSOR_I2C"},
      "speed_hz": 400000,
      "expect": {"instance": "non_empty"}
    },
    {
      "net": "SDA",
      "kind": "i2c",
      "role": "sda",
      "bus": {"instance": "i2c", "default": "SENSOR_I2C"},
      "speed_hz": 400000,
      "expect": {"instance": "as_given", "default": "controller"}
    }
  ],
  "hints": [{"net": "+VDD", "style": "trunk"}],
  "draws": [{"rail": "+VDD", "amps": 0.001, "note": {"instance": "draws", "default": "two pull-ups"}}],
  "waivers": [{"kind": "tp_waivers", "key": "SCL", "reason": "the bus is probed at the host header"}],
  "purpose": [
    {"part": "R1", "role": "pull", "pin": "U1.IO1"},
    {"part": "R2", "role": "pull", "net": "SDA"}
  ],
  "free": [{"part": "U1", "reason": "protection array; it is placed with the connector, not with a pin"}]
}
```

## 3. Key reference

The loader reads the sections in the order shown. "Required" means the loader fails if the key is absent. "Text" is a JSON string, possibly empty; "name" is a non-empty JSON string. The prefix `subsystem file <where>: ` is omitted from the loader messages below.

### 3.1 Top level

Every key in the table is required, except that `interface` is read only when the subsystem is registered or listed (`subsystem_data_definition`), not by `author_subsystem_data`. `placement` and `checks` are read by both (`subsystem_data_facts`), so a file without them fails when it is authored and when the library is listed. They are not part of the circuit: the generated `circuit.json` and `layout.json` do not carry them. Any other top-level key fails with `unknown key 'K' in <where>`. The key check runs before everything else.

| Key | Type | Meaning and errors |
|---|---|---|
| `schema` | text | Must be `schgen.subsystem/1`, else `schema is not schgen.subsystem/1`. Missing or non-text: `field 'schema' is missing or has the wrong type`; empty: `field 'schema' is empty`. |
| `name` | name | The subsystem name and circuit name. Must equal the folder name: `name X differs from its folder` (library listing, prefixed by the file path) or `its name differs from its folder X` (lookup by name). |
| `title` | name | Sheet title. An empty title fails with `field 'title' is empty`. |
| `interface` | array of names | The external names of the block: every non-signal net (power, ground, port). Read by `subsystem_data_definition`, not by `author_subsystem_data`; a bad entry fails with `'interface' holds a value that is not a name`. Its content is checked by the structure gate (section 6). |
| `placement` | object | Facts about where the subsystem's sheet is placed; section 3.11. Missing or not an object: `field 'placement' is missing or has the wrong type`. |
| `checks` | object | Facts the electrical checks read; section 3.12. Missing or not an object: `field 'checks' is missing or has the wrong type`. |
| `parts`, `nets`, `unconnected`, `ports`, `hints`, `draws`, `waivers`, `purpose`, `free` | array | Each must be present and an array (`field 'K' is missing or has the wrong type`); each entry of all but `unconnected` must be an object (`'K' holds a value that is not an object`). An empty array is accepted. |

### 3.2 `parts`

`ref` is required in both forms. The form is chosen by the presence of the key `part`.

**Catalogue form** (`part` present). Accepted keys: `ref`, `part`, `value`, `lcsc`, `symbol`, `footprint`, `fields`. Calls `CircuitAuthor::use_part`, then `field` for each entry of `fields`.

| Key | Type | Required | Meaning and errors |
|---|---|---|---|
| `ref` | name | yes | Reference designator. A repeat fails with `duplicate reference 'R1'`. |
| `part` | name | yes | Manufacturer part number in the part catalogue. Characters outside `A-Za-z0-9._-` are replaced by `_` (runs collapsed; leading and trailing `_` trimmed) to give the catalogue key. An unknown part fails with `catalog lookup failed: unknown mpn 'X'` (raised as `std::runtime_error`). With no catalogue resolver in the context: `use_part: no catalog resolver`. |
| `value` | text | no | Overrides the value. Default is the catalogue MPN. An empty string is ignored. |
| `lcsc` | text | no | LCSC code, used only when the catalogue has none for the part. The `LCSC` field is the catalogue code if it is non-empty, else this value, else empty. |
| `symbol` | text | no | Overrides the symbol (`lib_id`). Default is the catalogue symbol. When given, the part gets an `MPN` field (the catalogue MPN) and a `Datasheet` field (if the catalogue has one), and the catalogue's pin names and numbers are not loaded, so pins can be given by number only. |
| `footprint` | text | no | Overrides the footprint. Default is the catalogue footprint. |
| `fields` | object of text | no | Extra fields, set after the part is created; a key already present is overwritten. Errors: `part R1 fields is not an object`, `part R1 field K is not text`. |

A non-text value for `value`, `lcsc`, `symbol` or `footprint` fails with `field 'K' is not text`. An empty `footprint` or `symbol` string is also ignored as an override, but a `symbol` key that is present, even empty, still counts as given for the `MPN`, `Datasheet` and pin-data behaviour above.

**Inline form** (no `part`). Accepted keys: `ref`, `symbol`, `value`, `footprint`, `fields`. Calls `CircuitAuthor::part`.

| Key | Type | Required | Meaning and errors |
|---|---|---|---|
| `ref` | name | yes | As above, including `duplicate reference`. |
| `symbol` | name | yes | Symbol library id, for example `Device:R`. |
| `value` | name | yes | Part value. |
| `footprint` | name | yes | Footprint id. The loader requires it, so the footprint default that `CircuitAuthor::part` derives for `Device:R` and `Device:C` is not reachable from a file. |
| `fields` | object of text | no | Fields, same errors as above. Inline parts do not accept `lcsc`; put the code in `fields`. |

### 3.3 `nets`

Entry keys: `name`, `class`, `pins`. Calls `CircuitAuthor::net`.

| Key | Type | Required | Meaning and errors |
|---|---|---|---|
| `name` | name | yes | Net name. The same name in two entries merges the pin lists. |
| `class` | text | no | One of `power`, `ground`, `port`, `signal`; any other value fails with `unknown net class 'X'`. If a net is repeated with a different class: `net 'X' reclassified OLD->NEW`. |
| `pins` | array of names | yes | Pins on the net, each `REF.PIN`. May be empty. |

When `class` is omitted, `CircuitAuthor::classify` chooses it from the name. `ground` if the name starts with any of `GND`, `GNDA`, `GNDD`, `GNDPWR`, `AGND`, `DGND`, `PGND`, `VSS`, `CHASSIS_GND`. Otherwise `power` if it starts with `+`, equals `VBUS`, or starts with `VDD` or `VCC`. Otherwise `signal`. Prefix matching means `GND_SENSE` is ground. A port net is never inferred; give `"class": "port"`.

Pin form (`CircuitAuthor::expand_pin`). A pin is `REF.PIN`, split at the first `.`; both sides must be non-empty, else `bad pin spec 'X' (want 'REF.PIN')`. An unknown reference fails with `X: unknown part 'REF'`. Resolution of `PIN`:

- If the part has catalogue pin data (a catalogue part without `symbol`): the text is first matched against pin numbers; if none matches, against pin names. A name shared by several pins (for example `GND`, `NC`) expands to all of them. If neither matches: `X: <value> has no pin number or name 'PIN'`.
- Otherwise (inline part, or catalogue part with `symbol`): only pin numbers are accepted; names are not resolved. If the context has a pin resolver that knows the symbol, an unknown number fails with `X: <value> (<symbol>) has no pin number 'PIN'`; without one the number is accepted unchecked.

A pin already on another net fails with `R1.1 already on net 'A', cannot also join 'B'`. A pin is added to a net once.

### 3.4 `unconnected`

Array of names (pins, same form and name expansion as above). Calls `CircuitAuthor::nc`. A pin that carries a net fails with `R1.1 carries a net, cannot be NC`. Nets are read first, so this is the check that applies to a pin listed in both places.

### 3.5 `ports`

Calls `CircuitAuthor::port_type` for entries that create a port type (section 4.4). Accepted keys: `net`, `kind`, `pair_with`, `impedance`, `role`, `bus`, `speed_hz`, `level_v`, `expect`, `explicit`.

| Key | Type | Required | Meaning and errors |
|---|---|---|---|
| `net` | name | yes | A net declared above with class `port`, else `port_type('N'): not a declared PORT net` (raised only when the entry creates a port type, section 4.4). |
| `kind` | name | yes | One of `single`, `diff_pair`, `usb_hs_pair`, `tmds_pair`, `i2c`, `sd_bus`; else `port_type('N'): unknown kind 'K'`. |
| `pair_with` | text | per kind | The complementary port net. |
| `impedance` | whole number | per kind | Impedance; the unit is not stated in the code. Non-integer or non-number: `field 'impedance' is not a whole number`. |
| `role` | text | per kind | `scl` or `sda`, for `i2c`. |
| `bus` | text or per-board object | no | Bus group name (section 4.2). |
| `speed_hz` | whole number | no | Bus speed. Same type error as `impedance`. |
| `level_v` | number | per kind | Signal level (volts, by the key name). Else `port N level_v is not a number`. |
| `expect` | text or per-board object | no | The expected counterpart (section 4.1). |
| `explicit` | boolean | no | Forces a port type to be created (section 4.4). Else `port N explicit is not true or false`. |

Rules per kind (from `port_type`):

| Kind | Requires | Forbids or defaults |
|---|---|---|
| `single` | nothing | `pair_with` and `role` rejected |
| `diff_pair` | `pair_with`; `impedance` (`diff_pair needs explicit impedance=`) | `role` rejected |
| `usb_hs_pair` | `pair_with` | `impedance` defaults to 90; `role` rejected |
| `tmds_pair` | `pair_with` | `impedance` defaults to 100; `role` rejected |
| `i2c` | `role` of `scl` or `sda` (`i2c needs role='scl' or 'sda'`) | `pair_with` rejected |
| `sd_bus` | `level_v` (`sd_bus needs level_v=`) | `pair_with` and `role` rejected |

Messages are prefixed with `port_type('N'): `. A pair kind without `pair_with` fails with `<kind> needs pair_with=`; a `pair_with` that is not a declared port net fails with `pair_with 'X' is not a declared PORT net`; `pair_with` on a non-pair kind fails with `pair_with only valid for pair kinds, not 'K'`; `role` on a non-`i2c` kind fails with `role only valid for i2c`. `impedance`, `speed_hz`, `bus`, `expect` and `level_v` are accepted on any kind without further checks.

For a pair kind, the complement net is typed automatically with the same kind, `pair_with` pointing back, and the same `impedance`, `bus` and `expect`; `role`, `speed_hz` and `level_v` are not copied. A separate entry for the complement must produce the same type as the automatic one, else `retyped <old> -> <new> (conflict)` or `complement 'X' already typed ..., conflicts with ...`. A second, different type for one net fails with `retyped`.

### 3.6 `hints`

Entry keys `net` (name, required) and `style` (name, required). Calls `CircuitAuthor::hint`. The only style is `trunk`: `hint('N'): unknown style 'S' (known: ['trunk'])`. The net must exist: `hint('N'): not a declared net`. A second hint for a net replaces the first.

### 3.7 `draws`

Entry keys `rail` (name, required), `amps` (number, required), `note` (required; text or per-board object, section 4.3). A missing `note` fails with `a draw lacks its note`. Calls `CircuitAuthor::draws`: `draws('R'): not a declared net`; `draws('R'): not a POWER rail (<class>)`; `draws('R'): amps must be > 0`.

### 3.8 `waivers`

Entry keys `kind`, `key`, `reason`, all required names. Calls `CircuitAuthor::waive`. Accepted kinds: `tp_waivers`, `decap_waivers`, `pull_waivers`, `reset_waivers`, `strap_waivers`, `ep_waivers`, `thermal_waivers`, `part_rule_waivers`; else `unknown waiver kind 'K'`. The reason is trimmed; if blank, `K('KEY'): a reason is required`.

| Kind | `key` must be | Error |
|---|---|---|
| `thermal_waivers`, `part_rule_waivers` | a part reference (the whole key) | `unknown part 'KEY'` |
| `tp_waivers`, `pull_waivers`, `reset_waivers` | a declared net | `K('KEY'): not a declared net` |
| `decap_waivers`, `strap_waivers`, `ep_waivers` | a part reference, `REF.PIN` (only `REF` is checked), or a declared net | `K('KEY'): not a part ref, 'ref.pin', or declared net` |

A repeated kind and key replaces the reason. Which design rule honours each kind is not determined here.

### 3.9 `purpose`

See section 5. Entry keys `part`, `role`, `pin`, `net`, `module_net`.

### 3.10 `free`

Entry keys `part` and `reason`, both required names. Calls `CircuitAuthor::free`: `unknown part 'P'` for an unknown part. A part may appear once across `purpose` and `free` together. This and a blank reason are checked by `finish` after the file is read, with the prefix `layout intent of <name>: ` (`serves(P): the part already has a declaration`, `free(P): the part already has a declaration`, `free(P): a reason is required`).

### 3.11 `placement`

An object. Accepted keys: `region`, `silk_label`, `far_guard_mm`, `escape_basis`, `escape_escalates`, `reserves_edge`; any other fails with `unknown key 'K' in <name> placement`. Every key is required. Errors below carry the prefix `subsystem file <name> placement: `. Read by `subsystem_data_facts`; a sheet's region is read by `sheet_roles` (`native/include/schgen/sheet_roles.hpp`) through `load_subsystem_facts`.

| Key | Type | Meaning and errors |
|---|---|---|
| `region` | name | `board` or `under_module`: where the sheet's parts are placed. Another name fails with `field 'region' is 'X', not board or under_module`; empty: `field 'region' is empty`; not text: `field 'region' is missing or has the wrong type`. |
| `silk_label` | name or `null` | Text of the connector label on the silkscreen. `null` states that there is none. An empty string or a value of another type fails with `field 'silk_label' is neither null nor a name`. |
| `far_guard_mm` | number above zero or `null` | Guard distance in millimetres. `null` states that there is none. Else `field 'far_guard_mm' is neither null nor a number above zero`. |
| `escape_basis` | name or `null` | Reason a bottom-side part may stay in the escape region. `null` states that there is none. Else `field 'escape_basis' is neither null nor a name`. |
| `escape_escalates` | boolean | Else `field 'escape_escalates' is missing or has the wrong type`. |
| `reserves_edge` | boolean | Else `field 'reserves_edge' is missing or has the wrong type`. |

An absent key fails with `field 'K' is missing`; an explicit `null` or `false` is the statement that the fact does not apply. Of these keys, only `region` is read by `sheet_roles` so far; the others are loaded and validated and are not yet read by any other code.

### 3.12 `checks`

An object. Accepted keys: `dividers`, `divider_sources`, `iset_window_ma`; any other fails with `unknown key 'K' in <name> checks`. Every key is required. Errors below carry the prefix `subsystem file <name> checks: `.

| Key | Type | Meaning and errors |
|---|---|---|
| `dividers` | array of objects | Named divider limits. An empty array is accepted. A value that is not an object fails with `'dividers' holds a value that is not an object`. |
| `divider_sources` | array of names | Nets treated as divider sources. An empty array is accepted. Else `'divider_sources' holds a value that is not a name`. |
| `iset_window_ma` | `[low, high]` or `null` | The allowed current window in milliamps. `null` states that there is none. Anything other than two numbers with `0 < low < high` fails with `field 'iset_window_ma' is neither null nor [low, high]` or `field 'iset_window_ma' is not 0 < low < high`. |

A `dividers` entry accepts the keys `net`, `source`, `limits`, `why`; any other fails with `unknown key 'K' in <name> checks divider`. `net`, `source` and `why` are required names. `limits` is a required array of objects and must not be empty (`divider N states no limits`). A `limits` entry accepts `volts`, `lo`, `hi`, `tag` (other keys fail with `unknown key 'K' in <name> checks divider limit`). `volts` is a required number, `tag` a required name, `lo` and `hi` optional numbers (`field 'K' is not a number`). At least one of them must be present (`a limit of divider N states neither lo nor hi`), and when both are present `lo` must be below `hi` (`a limit of divider N has lo not below hi`). The loader stores these values; no check reads them yet.

## 4. Per-board settings

A board supplies a `SubsystemMeta` (`native/src/authoring.cpp`): a JSON object, or null for none, with only the keys `bind`, `expects`, `buses`, `notes` (else `unknown subsystem meta key(s) ['K'] — legal keys are ['bind', 'expects', 'buses', 'notes']`). Each section is an object or null (`subsystem meta['K'] must be a dict`); each value must be a string (`subsystem meta['K']['k'] must be a string`), except that `expects` values may also be null (message ends `or null`). A value in the file can come from the board in exactly three places.

### 4.1 Port `expect`

| File form | Board gives a value | Board gives `""` | Board gives nothing |
|---|---|---|---|
| plain text `"expect": "x"` | text from the file; the board is not consulted | same | same |
| `{"instance": "as_given", "default": "d"}` | the board's value | the empty string is kept as the expectation | `d` |
| `{"instance": "as_given"}` | the board's value | the empty string is kept | no expectation |
| `{"instance": "non_empty"}` | the board's value | no expectation | no expectation |

"Board gives nothing" means the key is absent from `expects`. A board `null` for the key means no expectation in the `as_given` forms (it overrides a default). In the `non_empty` form, null is also no expectation. The lookup key is `key` when given, otherwise the port's `net` name. Accepted object keys are `instance`, `key`, `default`; any other is `unknown key`. `instance` must be a name: `as_given` or `non_empty`, else `port N expect names an unknown per-board mode M`. `non_empty` with a `default` fails with `port N expect 'non_empty' takes no default`. A `default` that is not text fails with `port N expect default is not text`. Any `expect` value that is neither text nor object fails with `port N expect is neither text nor a per-board setting`.

### 4.2 Port `bus`

`"bus": "NAME"` is used as written. `"bus": {"instance": "<role>", "default": "NAME"}` uses the board's `buses[<role>]` when present, else `default`. Both keys are required and the only keys allowed; `default` must be text (it may be empty). An empty board value is used as is. `instance` is the name of a bus group, not a net: ports that share an `instance` take the same board value.

### 4.3 Draw `note`

`"note": "text"` is used as written. `"note": {"instance": "<key>", "default": "text"}` uses the board's `notes[<key>]` when present, else `default`. Same rules as `bus`. An empty board value is used as is.

A `bus` or `note` value that is neither text nor an object fails with `a value is neither text nor a per-board setting`. In the object, an unknown key fails with `unknown key 'K' in <where>`, a missing `instance` with `field 'instance' is missing or has the wrong type`, and a missing `default` with `field 'default' is missing or has the wrong type`.

### 4.4 Port types, `explicit`, and `bind`

A port entry creates a port type only if it carries information. The loader counts it as typed when `kind` is not `single`, or any of `pair_with`, `role`, `bus`, `expect`, `impedance`, `speed_hz`, `level_v` has a value after the board settings are applied. If it is typed, or `"explicit": true`, `port_type` is called. Otherwise the entry is ignored (including the check that the net is a port net), and the net has the implied type `single`. A consequence: `{"net": "N", "kind": "single", "expect": {"instance": "non_empty"}}` produces a port type only when the board gives a non-empty expectation. Add `"explicit": true` to create the type in every case.

`bind` renames nets after the whole file is read, so a file always uses its own abstract names. `SubsystemMeta::finish` calls `CircuitAuthor::bind` and then validates the layout. Rules:

- A source must be a net of the circuit: `bind: 'X' is not a net on circuit 'NAME'`.
- Only power, ground and port nets may be renamed; a signal net fails with `bind: 'X' is a private SIGNAL net — only POWER/GROUND/PORT (rail/port) externals are bindable; a subsystem's internal wiring is never rebound`.
- A target must be non-empty (`bind: target name must not be empty`).
- Two sources may not share a target (`bind: distinct externals cannot merge onto one net (LAW-0 short)`).
- A target may not be another net of the circuit that is not itself renamed (`bind: 'A' -> 'B' collides with the existing net 'B' on this circuit`).

The rename applies to net names, port types (`net` and `pair_with`), draws, hints, `purpose` nets, waiver keys except those of `thermal_waivers` and `part_rule_waivers`, and the `value` of parts whose symbol is `Connector:TestPoint` or `Mechanical:MountingHole_Pad`.

## 5. Purpose and roles

A `purpose` entry says which part a support part serves and in what role. `part` and `role` are required names. Exactly one of `pin`, `net`, `module_net` is required; none or more than one fails with `purpose of P names exactly one of pin, net and module_net`.

| Form | Calls | Meaning and errors |
|---|---|---|
| `"pin": "REF.PIN"` | `serves` | The part serves that pin of another part. The pin must resolve to exactly one physical pin (`X: names N stacked pins — this context needs exactly one`). The owner must be another part (`a part cannot serve itself`), share a net with the part (`shares no net with its owner REF.PIN`), and ownership may not form a cycle. |
| `"net": "NAME"` | `serves_net` | The part serves a net. The net must be declared (`serves_net('P'): 'N' is not a declared net`) and the part must have a pin on it (`the part has no pin on net 'N'`). |
| `"module_net": "NAME"` | `serves_module` | As `net`, and the entry carries the target `module` (`serves_module('P'): 'N' is not a declared net`). The layout adapter passes this as a `module` flag on the service. |

An unknown part fails with `unknown part 'P'`. Role and structure errors from `validate_circuit_layout` are raised by `finish` with the prefix `layout intent of <name>: `, for example `serves(P): unknown role 'R'`. The separate layout-intent gate (`check_layout_intent`, run by the board pipeline) fails for every part whose symbol starts with `Device:` that is in neither `purpose` nor `free`.

Roles are listed in one place, `native/src/roles.cpp`; reach values are in `native/include/schgen/roles.hpp` (mm, basis `policy`). The reach is the distance read by the placement rules for that role (`role_reach` in `native/src/layout_adapter.cpp`). The description is the reason given beside each constant.

| Role | Reach (mm) | What it is for |
|---|---|---|
| `bypass` | 2.0 | Bypass capacitor; loop inductance rises about 1 nH per mm. |
| `reservoir` | 6.0 | Bulk capacitance; works at lower frequency, serves a pin several mm away. |
| `pull` | 12.0 | Pull resistor; only sets a level, distance costs stub length. |
| `series` | 4.0 | Series element; belongs at the source so the trace beyond it is the damped line. |
| `terminate` | 3.0 | Termination; further from its receiver leaves an unterminated stub. |
| `limit` | 8.0 | Current-limiting resistor at a connector; guards the parts behind it. |
| `filter` | 4.0 | Filter element; works on the node it touches. |
| `feedback` | 4.0 | Feedback and compensation nodes; high impedance, short traces keep switching noise out. |
| `switching` | 3.0 | Switching power loop; its area sets ringing and radiated noise. |
| `timing` | 3.0 | Crystal and timing parts; traces add load capacitance and pick up noise. |
| `protect` | 6.0 | Clamp; must meet the surge before the pin it protects. |
| `sense` | 6.0 | Sense element; traces carry small differential voltages. |
| `indicate` | 15.0 | Indicator; carries a slow signal and may sit where it is visible. |
| `set` | 6.0 | Programming element; sets a quiet node. |

## 6. How to add a subsystem

1. Create `subsystems/<name>/` at the repository root. The structure gate skips folders whose names start with `.` or `_` and names ending in a space and digits (such as `name 2`). It checks every other folder under `subsystems/` as a package, so a folder without `subsystem.json` fails it (`native authoring factory unavailable: <name>`).
2. Write `subsystems/<name>/subsystem.json` with `"name": "<name>"`. Give it `placement` and `checks` with the neutral values of the example in section 2 unless a fact applies. Parts named by `part` must exist in the part catalogue (`parts/<MPN>/part.json`; `schgen run` and `schgen board-check` compile `parts/` into `native/catalog.bin` at run time, so a new catalogue part needs no rebuild of the application).
3. Add the other files the structure gate requires. For a library package (`AuthoringPackageMode::native_assets`, the mode used by the board pipeline and by the `subsystem-check` command) `check_subsystem_package` requires two regular files in the folder: `README.md` and `<name>.cir`. A missing file is reported as missing. Nothing else is required; for example `placement_contract.json` is not checked by this gate. If the folder also holds `circuit.json`, it must match the built circuit, and then `layout.json` must exist and match too (`circuit.json differs from the native authoring factory`, `layout.json is missing beside circuit.json`, `layout.json differs from the native authoring factory`).
4. Make `interface` match the circuit. The gate builds the circuit with empty board settings and requires: a non-empty `interface`, no duplicate names (`duplicate name in native INTERFACE`), every non-signal net listed (`net 'X' is an external but not in the declared INTERFACE`), and no listed name that is not such a net (`INTERFACE name 'X' is not an external net of the built circuit`). A build failure is reported as `circuit() build failed: <message>`.
5. Run the application. No rebuild is needed: the file is read when the subsystem is requested. A board uses it by name with its own `SubsystemMeta` (section 4).

## 7. Component basis files

The component basis audit checks that every resistor, capacitor and inductor value, and every port speed and impedance, in the built circuits is backed by a written engineering basis. The audit's inputs are data: one file for the library and one per board. The application reads them when it runs; `load_component_basis_policy` takes the repository root and fails with a message naming the file and the row when a file is missing or malformed. Every file has `"schema": "schgen.component_basis/1"`, and a key outside the lists below is rejected.

`subsystems/component_basis.json` holds the shared declarations and the library scope. It has these keys, all required:

| Key | Contents |
|---|---|
| `declarations` | Rows of `name`, `value`, `unit`, `basis`, `class` and `numeric` (a boolean). The text keys must not be empty. A name may not be listed twice. A row may be used by several subsystems and several boards. |
| `uses` | Rows of `sheet`, `target`, `attribute`, `declaration` and `type`: one obligation each. `sheet` must be in this file's `sheets`, and `declaration` must be a declared name. |
| `sheets` | Library subsystems audited in the `library` scope, built with empty settings. A name may not be listed twice. |
| `board_scope_only` | Library subsystems audited only under the boards that use them. A name may not be listed twice. |

Each board folder holds a `component_basis.json` with `schema`, `uses` and `sheets` only; a `declarations` or `board_scope_only` key is rejected. The scope of a board is its folder name. Its `uses` may name any declaration in `subsystems/component_basis.json` but only sheets in its own `sheets`. A board file is required for every folder that holds a `board.json`. The loaded policy lists the library rows first, then each board in folder order, keeping the file order within each scope.

Every library subsystem must be accounted for exactly once. A library subsystem in `sheets` is audited in the `library` scope. One in `board_scope_only` is not audited there. One in neither, or in both, fails with `library subsystem X is neither in sheets nor in board_scope_only of <file>` (or `is in both sheets and board_scope_only of <file>`). A name in `sheets` or `board_scope_only` that is not a library subsystem fails, naming it. A name in `board_scope_only` that is in the `sheets` of no board file fails, so it cannot go unaudited. Every board sheet is audited in the board's scope; a board sheet missing from its file's `sheets` fails as an unexpected live sheet.

When you add a library subsystem, list it in `sheets` (with its obligations in `uses`) or in `board_scope_only`. The audit does not pass until you do.

## 8. The module folder

Every board names the folder of the module it carries in `board.json`, under `module.folder` (for example `"folder": "som"`). The folder sits at the repository root and holds `module.json` and `som_interface.json` beside the module's own KiCad project. `board.json` `module` then holds only what belongs to the board: `pairs` on nets the board maps from module pins, and `loads` on the module's supply pins.

`module.json` has these keys, all required, and any other key is rejected:

| Key | Contents |
|---|---|
| `schema` | `schgen.module/1`. |
| `schematic`, `pcb` | File names of the module's KiCad schematic and board inside the module folder. A path separator is rejected. |
| `connector_part` | The part name of the module connector. |
| `controller_ref`, `fpga_ref` | The reference designators, in the module's own schematic, of its controller and of its FPGA or processor. They differ. The pin constraints file, the controller pin map in the manifest and the module pin map read them from here. |
| `draw` | `connector`, `rail`, `amps` and `note`: the module's own current draw. `rail` is the module net; a board's `rebound_som_rails` maps it to the board net. |
| `sdio_level_v`, `sd_bus` | The module's SD bus signal level and its net names. |
| `pairs` | Differential pairs on module pin nets, as in `board.json`. They come before the board's own pairs. |
| `escape_population` | `netted_contacts` (contacts per connector reference) and `return_path` (`n_pairs`, `n_pair_contacts`, `n_fail`, `worst_distance`): the measured populations the escape and return-stitch gates compare the live module against. |
| `escape_triage` | Rules `pattern`, `class` and `note` for module pin nets. They are tried after the rules in the board's own `escape_triage.json`. |
| `do_not_load_straps` | Module pin nets that must stay unmapped in every board's `som_mapping.json`. |
| `supplies` | Rails the module delivers to the board: `rail` (module net, mapped through the board's `rebound_som_rails`), `volts`, `amps` and a required `basis`. Every board must take each one in its `power.sources` (see section 10, board power). |
| `regulated_rails` | `rails`, the module nets the module regulates on-module without delivering them, and `basis`, the text of the parallel-source finding the power-tree gate raises when a board regulator outputs one of those rails on a module connector sheet. |

`som_interface.json` is written by `schgen som-interface` into the module folder. A board's `som_mapping.json` and `escape_triage.json` hold only the board's own decisions; `do_not_load_straps` in `som_mapping.json` is rejected.

## 9. Sheet roles

`sheet_roles` (`native/include/schgen/sheet_roles.hpp`) builds one table for a board: for each sheet of `board.json`, the module connector it carries (empty for an ordinary sheet) and its region. The module connector comes from the sheet's `module_connector` in `board.json`. The region of an ordinary sheet comes from `placement.region` of its `subsystem.json` in the library (`load_subsystem_facts`); a missing file fails with `unknown subsystem N`. A module connector sheet has no subsystem file and its region is `board`. `sheet_role` returns the entry for a sheet and throws `sheet roles: no role for sheet N` for a sheet the table lacks.

The table is built from the board definition, the library, the module interface (`som_interface.json` of the module folder), the authored circuits and the part facts, and it throws, naming the board and the sheet, when the data disagree:

| Check | Message |
|---|---|
| A module connector sheet has no authored circuit. | `board B sheet S: the module connector sheet has no circuit` |
| The sheet holds other than one part. | `board B sheet S: a module connector sheet holds exactly one part, this one holds N` |
| The part's reference differs from the sheet's `module_connector`. | `board B sheet S: its part is R but board.json states module_connector C` |
| The part's class (from the part facts) is not `module_connector`. | `board B sheet S: its part R has class K, not module_connector` |
| Two sheets carry the same connector. | `board B sheet S: module connector C is also carried by sheet T` |
| A sheet names a connector the module interface lacks. | `board B sheet S: module connector C is not a connector of the module interface F` |
| The module interface has a connector that no sheet carries. | `board B: no sheet carries module connector C of the module interface F` |

## 10. Board power

`board.json` `power` is required, with exactly these keys:

| Key | Contents |
|---|---|
| `sources` | The board's power sources in report order. A row is either `{"rail", "volts", "amps", "basis"}` (a source the board owns, such as a USB-C PD contract) or `{"rail", "supplier": "module"}` (a rail from the module's `supplies`; its values come only from `module.json`). |
| `rails` | `{"rail", "volts", "basis"}` rows: `volts` is a number or `null` (a rail stated to have no voltage). Use a row for a rail the tool cannot compute: the target of an adjustable regulator, a connector-supplied or cable-supplied net, a part with no `regulators` row. |
| `inlet` | `{"rail", "bulk"}`: the receptacle rail and the bulk rail behind its eFuse, for the pre-contract capacitance audit; or `null` for a board with no such inlet. |

Every row needs a `basis`; unknown keys are rejected and a rail may appear once in `sources` and `rails` together. Example: `{"rail": "+5V_REG", "volts": 5.0, "basis": "LM61460 power:U1 set-point target; ..."}`.

The voltage of every net is resolved in this order, and each rail has exactly one home:

1. a source row;
2. a `rails` row;
3. a producer, repeated until nothing changes: a regulator with `out_v` in `parts/part_facts.json` gives that voltage; a regulator of kind `load_switch` or `efuse` passes its input rail's voltage; a power-tree bridge (a part on exactly two power nets) whose part class is `resistor`, `inductor` or `ferrite` passes the voltage of its other end.

A regulator with `fb_vref` (an adjustable output) is not a home: its output needs a `rails` row stating the target, and the spice gate checks the divider set point (`fb_vref x (1 + Rtop/Rbottom)`) against that target. The load fails, naming the rails, when: a power-class net has no home; an adjustable output has no target (the message gives the divider value); a rail has two homes; a bridge joins two different voltages; a row names a net no sheet of the board has; a `supplier: module` row names no module supply; or a module supply is not taken by the board. A net of another class has a voltage only from a `rails` row.

## 11. Copper claims

The copper-debt ledger (`reports/copper_debt.txt`) lists the engineering claims that rest on copper the board must carry. The claims, the checks that tie each claim to the live circuits and policies, and the measurement of the emitted board are data in `subsystems/copper_claims.json`. `load_copper_claims` takes the repository root and fails with a message naming the file, the claim and the key when the file is missing or malformed. Any key or kind not listed below is rejected. The `where:` line of a claim in the report is `subsystems/copper_claims.json#<id>`.

Top-level keys, all required: `schema` (`schgen.copper_claims/1`), `plane`, `inventory`, `claims`.

| Key | Contents |
|---|---|
| `plane` | `net` and `layer` of the ground plane every measure refers to. |
| `inventory` | `with_text`, `without_text` and `emits`, the text of the inventory line. `emits` may use `{fills}`, `{plane}`, `{rules}`, `{vias}`, `{gnd}`, `{segments}`. |
| `claims` | Non-empty list, in report order. Each claim has `id` (unique), `title`, `assumes`, `risk`, `checks` (non-empty) and `measure`. |

A claim is verified on every run, with or without a PCB. Any check that fails raises `CopperProvenanceError` naming the claim. Thermal figures, pour needs, exposed-pad via needs and isolation margins are read from `parts/part_facts.json` rows. A claim states the figures it relies on (`thermal_fact`, `thermal_credit` `need`) and the check fails when a row differs.

Check kinds. The sheet kinds take `scopes` (the `library` and board folder names to check; each must exist, and each listed sheet and part must exist in each listed scope) and `sheet`.

| Kind | Other keys | Fails when |
|---|---|---|
| `part` | `refs` (list) or `all_parts` (true); optional `lib_id`, `footprint`, `value_prefix`, `fields` (name to value), `pins` (rows of `pin` and one of `net`, `net_prefix`) | a listed part is missing, or one given attribute, field or pin connection differs. `all_parts` needs at least one attribute. |
| `net_pins` | `net`, `pins` (rows of `[reference, pin]`) | a listed part is missing or a pin is not on the net. |
| `part_count` | `count` | the sheet does not hold that many parts. |
| `thermal_fact` | `refs`, `rth_ja`, `rth_ja_pour` (number or null), `pour_evidence` | the part has no `thermal` row, a figure differs, or the row has no citation. |
| `part_fact` | `refs`, `section` (`ep_vias` or `isolation`) | the part has no row in that section. |
| `thermal_credit` | `part` (MPN), `need` (`min_vias`, `radius_mm`, `pour_layers`: the copper the claim states) | the part's `thermal_copper` need, the thermal pour need or the emitter pour need differs from the claim's `need`, the pour field is short of it or lacks a citation, or the part has no pour credit. |
| `emission_via` | `size_mm`, `drill_mm` | the emitter's thermal via differs. |
| `emission_ground_layer` | `layer` | the emitter's ground layer differs. |
| `isolation_margins` | none | the isolation facts are empty or one has no positive margin. |
| `impedance_geometry` | `impedance_ohm` | the researched differential geometry differs from the live one or the ground reference is missing. |

Measure kinds. Each takes every key listed; text keys are templates and may use only the placeholders named.

| Kind | Keys |
|---|---|
| `thermal_via_field` | `part` (MPN; its instances are found by its `regulators` label; radius, via count and pour layers come from its `thermal_copper` need), `emits` (`{plane}`, `{rows}`), `row` (`{ref}`, `{count}`, `{radius}`), `pour` (`{layer}`, `{state}`, appended to a row once per pour layer) |
| `ep_via_pads` | `part`, `emits` (`{plane}`, `{rows}`), `row` (`{ref}`, `{count}`); pad count and radius come from the `ep_vias` row |
| `net_island` | `net`, `emits` (`{zones}`, `{vias}`) |
| `plane_voids` | `zone_prefix`, `min_voids_with_plane`, `none_text`, `emits` (`{names}`) |
| `reference_plane` | `emits` (`{x0}`, `{y0}`, `{x1}`, `{y1}`), `absent_emits` |
| `module_body_vias` | `zone_prefix`, `found_text`, `missing_text`, `emits` (`{count}`, `{zone}`) |

Add a claim by appending a row with its checks and a measure; the ledger and the report follow the file.
