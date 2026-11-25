"""Bound keys and prompts as glyphs on Prey's retained pages
(docs/dev/prey-ui-visual-design.md section 12.5, "Options").

Ported from openQ4's tools/ui/retained_key_glyphs.py and recoloured for
Prey's steel glass: a keyboard key is a keycap with the 45-degree cut, a dark
`#111A25` plate under a `prey.rail` edge with the key's name in pale ink; the
arrow keys draw their arrow, the mouse its body with the bound button lit, and
a controller button the glyph of the family in use, in the same plate, edge
and ink. Nothing here adds a hue: every mark is the rail's pale blue-white.

The engine resolves what to draw (src/ui/UserInterfaceRetained.cpp): a key
state holds the key's label and "<state>.glyph" its kind (PromptGlyph);
"<state>.arrow" names an arrow key; "<state>.keyCount" and ".padCount" how
many keys of each family the action has
(idUserInterfaceRetained::SetKeyBindingNames).

A chip is sized in em of its strip, whose font size is the chip's height, so
a page that grows its rows grows the strip's one length and every chip
follows; the art is drawn in fractions of each glyph's box. Every slot repeats
the same art, so the art is the document's shared symbols, and a slot draws
whichever its kind names through one vector whose `symbol` is bound.

The module is self-contained: it takes the generator's Document (its
`state`, `symbols` and `bind(node, prop, value)`) and builds plain nodes."""
from __future__ import annotations

BOX = 22.0                    # dp: the box the art is drawn in
GAP = 0.22                    # em between chips
GROUP_GAP = 0.3               # em more between the last keyboard or mouse key and the first controller button
BODY = "chain"                # the body face (build_retained_screens.BODY)
PLACEHOLDER = "#str_20128"    # a bound text's key before its first binding


def rgb(code: str, alpha: float = 1.0) -> list[float]:
    code = code.lstrip("#")
    return [round(int(code[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)] + [alpha]


CAP_FILL = rgb("#111A25", 0.88)     # the header bar's dark steel
CAP_EDGE = rgb("#B3C6E2")           # prey.rail
CAP_INK = rgb("#DCE7F5")            # the key's name and every mark
CAP_LIT = rgb("#B3C6E2", 0.95)      # a bound mouse button, a lit d-pad arm
EDGE_W = 1.2                        # dp

# The glyph kinds (UserInterfaceRetained.cpp PromptGlyph).
KEYCAP, LETTER = 0, 1
CROSS, CIRCLE, SQUARE, TRIANGLE = 2, 3, 4, 5
SOUTH, EAST, WEST, NORTH = 6, 7, 8, 9
BUMPER, TRIGGER = 10, 11
DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT = 12, 13, 14, 15
STICK, MENU, VIEW, HOME, TOUCHPAD, PADDLE, BUTTON = 16, 17, 18, 19, 20, 21, 22
MOUSE_LEFT, MOUSE_RIGHT, MOUSE_MIDDLE, WHEEL_UP, WHEEL_DOWN, MOUSE_SIDE = 23, 24, 25, 26, 27, 28
# The kinds whose label the engine supplies and one shared label draws.
LABELLED = (LETTER, BUMPER, TRIGGER, STICK, PADDLE)

# The controller families the prompt state names (RetainedUI_PromptGlyphs:
# 0 is the keyboard, 1-5 these in order).
FAMILIES = ("xbox", "playstation", "nintendo", "steamdeck", "generic")
FACE_LETTERS = {
    "xbox": {"south": "A", "east": "B", "west": "X", "north": "Y"},
    "nintendo": {"south": "B", "east": "A", "west": "Y", "north": "X"},
    "steamdeck": {"south": "A", "east": "B", "west": "X", "north": "Y"},
}
PS_SYMBOLS = {"south": "cross", "east": "circle", "west": "square", "north": "triangle"}
SHOULDER_LABELS = {"xbox": ("LB", "RB"), "playstation": ("L1", "R1"), "nintendo": ("L", "R"), "steamdeck": ("L1", "R1"),
                   "generic": ("L1", "R1")}
# Fixed button and key names as language keys (a retained document's text
# must name one): the same in every language.
LABEL_KEYS = {"Q": "#str_122216", "E": "#str_122217", "LB": "#str_122218", "RB": "#str_122219", "L1": "#str_122220", "R1": "#str_122221", "L": "#str_122222", "R": "#str_122223", "LT": "#str_122224", "RT": "#str_122225", "L2": "#str_122226", "R2": "#str_122227", "ZL": "#str_122228", "ZR": "#str_122229"}
TRIGGER_LABELS = {"xbox": ("LT", "RT"), "playstation": ("L2", "R2"), "nintendo": ("ZL", "ZR"), "steamdeck": ("L2", "R2"),
                  "generic": ("L2", "R2")}


# ------------------------------------------------------------ typed values

def length(value: float, unit: str = "dp") -> dict:
    return {"type": "length", "value": round(value, 4), "unit": unit}


def em(value: float) -> dict:
    return length(value, "em")


def keyword(value: str) -> dict:
    return {"type": "keyword", "value": value}


def number(value: float) -> dict:
    return {"type": "number", "value": value}


def solid(value: list[float]) -> dict:
    return {"type": "solid", "color": {"type": "color", "value": value}}


def stroke(value: list[float], width: float) -> dict:
    return {"paint": solid(value), "widthDp": round(width, 3), "minimumPixels": 1, "join": "round", "cap": "round"}


def group(ident: str, props: dict, children=()) -> dict:
    node = {"id": ident, "type": "group", "properties": props}
    if children:
        node["children"] = list(children)
    return node


def text_node(ident: str, props: dict, key: str = PLACEHOLDER) -> dict:
    return {"id": ident, "type": "text", "properties": {"text": {"type": "text", "value": key}, **props}}


# ------------------------------------------------------------------- paths

def path(ident: str, points: list, *, fill=None, line=None, closed: bool = True, **paint) -> dict:
    line = paint.get("stroke", line)
    commands = [{"id": f"p{index}", "op": "move" if index == 0 else "line", "points": [list(at)]}
                for index, at in enumerate(points)]
    if closed:
        commands.append({"id": "z", "op": "close"})
    result = {"id": ident, "commands": commands}
    if fill is not None:
        result["fill"] = fill
    if line is not None:
        result["stroke"] = line
    return result


def circle(ident: str, cx: float, cy: float, r: float, *, fill=None, line=None, **paint) -> dict:
    """A circle as four cubic quarter arcs."""
    line = paint.get("stroke", line)
    k = 0.5523 * r
    at = lambda dx, dy: [cx + dx, cy + dy]
    result = {"id": ident, "commands": [
        {"id": "m", "op": "move", "points": [at(r, 0)]},
        {"id": "a", "op": "cubic", "points": [at(r, k), at(k, r), at(0, r)]},
        {"id": "b", "op": "cubic", "points": [at(-k, r), at(-r, k), at(-r, 0)]},
        {"id": "c", "op": "cubic", "points": [at(-r, -k), at(-k, -r), at(0, -r)]},
        {"id": "d", "op": "cubic", "points": [at(k, -r), at(r, -k), at(r, 0)]},
        {"id": "z", "op": "close"}]}
    if fill is not None:
        result["fill"] = fill
    if line is not None:
        result["stroke"] = line
    return result


def rounded(ident: str, x: float, y: float, w: float, h: float, r: float, *, top_only: bool = False, **paint) -> dict:
    """A rounded rectangle as cubic corners; `top_only` leaves the lower corners square."""
    k = 0.5523 * r
    right, bottom = x + w, y + h
    commands = [("move", [(x, bottom - (0 if top_only else r))]), ("line", [(x, y + r)]),
                ("cubic", [(x, y + r - k), (x + r - k, y), (x + r, y)]), ("line", [(right - r, y)]),
                ("cubic", [(right - r + k, y), (right, y + r - k), (right, y + r)])]
    if top_only:
        commands += [("line", [(right, bottom)]), ("line", [(x, bottom)])]
    else:
        commands += [("line", [(right, bottom - r)]), ("cubic", [(right, bottom - r + k), (right - r + k, bottom), (right - r, bottom)]),
                     ("line", [(x + r, bottom)]), ("cubic", [(x + r - k, bottom), (x, bottom - r + k), (x, bottom - r)])]
    result = {"id": ident, "commands": [{"id": f"c{index}", "op": op, "points": [list(p) for p in points]}
                                        for index, (op, points) in enumerate(commands)] + [{"id": "z", "op": "close"}]}
    result.update(paint)
    return result


def _fractions(paths: list, width: float) -> list:
    """Art drawn in dp in a `width` x BOX box, in fractions of it."""
    def convert(value, extent):
        return {"fraction": round(value / extent, 5)} if isinstance(value, (int, float)) else value
    for drawn in paths:
        for command in drawn["commands"]:
            if "points" in command:
                command["points"] = [[convert(at[0], width), convert(at[1], BOX)] for at in command["points"]]
    return paths


PLATE = {"fill": solid(CAP_FILL), "stroke": stroke(CAP_EDGE, EDGE_W)}


# --------------------------------------------------------------- face marks

def face_mark(prefix: str, mark: str, scale: float = 1.0, ink: list | None = None) -> list:
    """A face button's letter or symbol drawn as strokes in a 22 dp box."""
    line = stroke(ink or CAP_INK, 1.8 * scale)

    def poly(name: str, points: list, closed: bool = False) -> dict:
        return path(f"{prefix}-{name}", [(x * scale, y * scale) for x, y in points], line=line, closed=closed)

    def curve(name: str, commands: list) -> dict:
        built = [{"id": f"c{index}", "op": op, "points": [[x * scale, y * scale] for x, y in points]}
                 for index, (op, points) in enumerate(commands)]
        return {"id": f"{prefix}-{name}", "commands": built, "stroke": line}
    if mark == "A":
        return [poly("a1", [(7.4, 15.5), (11, 6.5), (14.6, 15.5)]), poly("a2", [(8.8, 12.3), (13.2, 12.3)])]
    if mark == "B":
        return [curve("b1", [("move", [(8.2, 15.5)]), ("line", [(8.2, 6.5)]), ("line", [(11.3, 6.5)]),
                             ("cubic", [(13.7, 6.5), (13.7, 10.9), (11.3, 10.9)]), ("line", [(8.2, 10.9)])]),
                curve("b2", [("move", [(8.2, 10.9)]), ("line", [(11.8, 10.9)]),
                             ("cubic", [(14.5, 10.9), (14.5, 15.5), (11.8, 15.5)]), ("line", [(8.2, 15.5)])])]
    if mark == "X" or mark == "cross":
        a, b = (7.6, 14.4) if mark == "X" else (7.3, 14.7)
        return [poly("x1", [(a, a), (b, b)]), poly("x2", [(b, a), (a, b)])]
    if mark == "Y":
        return [poly("y1", [(7.6, 6.6), (11, 11.2), (14.4, 6.6)]), poly("y2", [(11, 11.2), (11, 15.4)])]
    if mark == "circle":
        return [circle(f"{prefix}-o", 11 * scale, 11 * scale, 4.5 * scale, line=line)]
    if mark == "square":
        return [poly("s", [(7.3, 7.3), (14.7, 7.3), (14.7, 14.7), (7.3, 14.7)], closed=True)]
    if mark == "triangle":
        return [poly("t", [(11, 6.3), (15.5, 14.5), (6.5, 14.5)], closed=True)]
    raise ValueError(mark)


def face_paths(family: str, position: str, scale: float = 1.0) -> list:
    """One family's face button at `position`: Xbox and Nintendo print their
    letters on a disc, PlayStation its four symbols, Steam Deck letters in a
    ring, and a generic controller the four positions as a diamond with this
    one filled."""
    s = scale
    if family == "generic":
        paths = []
        for spot, (cx, cy) in (("north", (11, 4.3)), ("west", (4.3, 11)), ("east", (17.7, 11)), ("south", (11, 17.7))):
            if spot == position:
                paths.append(circle(f"dot-{spot}", cx * s, cy * s, 3.6 * s, fill=solid(CAP_LIT)))
            else:
                paths.append(circle(f"dot-{spot}", cx * s, cy * s, 2.7 * s, line=stroke(CAP_EDGE, 1.2 * s)))
        return paths
    if family == "steamdeck":
        return [circle("ring", 11 * s, 11 * s, 9.9 * s, fill=solid(CAP_FILL), line=stroke(CAP_EDGE, 1.4 * s)),
                *face_mark("mark", FACE_LETTERS[family][position], s)]
    mark = PS_SYMBOLS[position] if family == "playstation" else FACE_LETTERS[family][position]
    return [circle("disc", 11 * s, 11 * s, 10.2 * s, **PLATE), *face_mark("mark", mark, s)]


# ------------------------------------------------------------------ chips

def _art(doc, ident: str, symbol: str, width: float, draw) -> dict:
    """One glyph: a flex item `width` dp wide in the BOX-high box, hidden
    until its kind is the slot's. Its art is the document's `symbol`."""
    if symbol not in doc.symbols:
        doc.symbols[symbol] = _fractions(draw(), width)
    return {"id": ident, "type": "vector", "symbol": symbol,
            "properties": {"display": keyword("none"), "width": em(width / BOX), "height": em(1)}}


def _show(doc, node: dict, condition: dict, shown: str = "block") -> dict:
    doc.bind(node["id"], "display", {"op": "select", "args": [condition, shown, "none"]})
    return node


def _is(state: str, value: int) -> dict:
    return {"op": "==", "args": [{"state": state}, value]}


def _any(state: str, values: tuple) -> dict:
    result = _is(state, values[0])
    for value in values[1:]:
        result = {"op": "||", "args": [result, _is(state, value)]}
    return result


def _text(ident: str, size: float, more: dict | None = None, key: str = PLACEHOLDER) -> dict:
    """Pale body face `size` dp tall in a BOX-high line, in em of the strip."""
    return text_node(ident, {"position": keyword("relative"), "display": keyword("block"),
                             "font-family": {"type": "font", "value": BODY}, "font-size": em(size / BOX),
                             "line-height": em(BOX / size), "color": {"type": "color", "value": CAP_INK},
                             "white-space": keyword("nowrap"), "text-align": keyword("center"), "pointer-events": keyword("none"),
                             **(more or {})}, key)


def cap_outline(shape: str) -> dict:
    """A plate as wide as its box: the keycap with its 45-degree cut at the
    lower leading corner ("key"), or a controller's labelled button, a
    lozenge ("button")."""
    full, most = {"fraction": 1}, {"fraction": 1, "dp": -5}
    if shape == "key":
        return path("cap", [(0.6, 0.6), ({"fraction": 1, "dp": -0.6}, 0.6), ({"fraction": 1, "dp": -0.6}, {"fraction": 1, "dp": -0.6}),
                            (5.5, {"fraction": 1, "dp": -0.6}), (0.6, {"fraction": 1, "dp": -5.5})], **{
                                "fill": solid(CAP_FILL), "line": stroke(CAP_EDGE, EDGE_W)})
    half = {"fraction": 0.5}
    return path("cap", [(5, {"fraction": 0.14}), (most, {"fraction": 0.14}), (full, half), (most, {"fraction": 0.86}),
                        (5, {"fraction": 0.86}), (0, half)], fill=solid(CAP_FILL), line=stroke(CAP_EDGE, EDGE_W))


def _cap(doc, ident: str, state: str | None, shape: str, key: str | None = None) -> dict:
    """A plate as wide as its label. Its label is `state`'s text, or the
    fixed `key`."""
    whole = {"position": keyword("absolute"), "left": length(0), "top": length(0), "width": length(100, "%"),
             "height": length(100, "%"), "pointer-events": keyword("none")}
    name = _text(f"{ident}-name", 14, key=key or PLACEHOLDER)
    if state:
        doc.bind(f"{ident}-name", "text", {"state": state})
    return group(ident, {"position": keyword("relative"), "display": keyword("block"), "height": em(1), "min-width": em(1),
                         "padding-left": em(0.3), "padding-right": em(0.3), "flex-shrink": number(0)},
                 [{"id": f"{ident}-plate", "type": "vector", "properties": whole, "paths": [cap_outline(shape)]}, name])


def _arrow(direction: int) -> list:
    """An arrow key's keycap: the plate and the arrow, 1 up, 2 down, 3 left, 4 right."""
    arrow = [(0, -6.0), (5.0, -0.6), (1.8, -0.6), (1.8, 6.0), (-1.8, 6.0), (-1.8, -0.6), (-5.0, -0.6)]
    turned = {1: lambda x, y: (x, y), 2: lambda x, y: (-x, -y), 3: lambda x, y: (y, -x), 4: lambda x, y: (-y, x)}[direction]
    return [path("cap", [(0.6, 0.6), (BOX - 0.6, 0.6), (BOX - 0.6, BOX - 0.6), (5.5, BOX - 0.6), (0.6, BOX - 5.5)],
                 fill=solid(CAP_FILL), line=stroke(CAP_EDGE, EDGE_W)),
            path("arrow", [(11 + dx, 11 + dy) for dx, dy in (turned(x, y) for x, y in arrow)], fill=solid(CAP_INK))]


MOUSE_W = 16.0


def _mouse(kind: int) -> list:
    """The mouse from above with the bound button lit: its left, right or
    middle button, the wheel with an arrow for a turn up or down, or a side
    button's nub at its flank."""
    left, top, width, height, split, middle = 2.0, 1.0, 12.0, 20.0, 9.6, 8.0
    lit = solid(CAP_LIT)
    seam = stroke(CAP_EDGE, 1.0)
    paths = [rounded("body", left, top, width, height, 5.6, fill=solid(CAP_FILL), stroke=stroke(CAP_EDGE, EDGE_W))]
    if kind in (MOUSE_LEFT, MOUSE_RIGHT):
        sign, edge = (-1, left + 1.4) if kind == MOUSE_LEFT else (1, left + width - 1.4)
        paths.append({"id": "button", "fill": lit, "commands": [
            {"id": "m", "op": "move", "points": [[middle + sign * 0.8, top + 1.4]]},
            {"id": "a", "op": "cubic", "points": [[edge - sign * 2.2, top + 1.4], [edge, top + 3.4], [edge, top + 6.0]]},
            {"id": "b", "op": "line", "points": [[edge, split - 1.0]]},
            {"id": "c", "op": "line", "points": [[middle + sign * 0.8, split - 1.0]]}, {"id": "z", "op": "close"}]})
        paths.append(path("seam", [(middle, top + 1.4), (middle, split)], closed=False, line=seam))
    else:
        paths.append(path("seam", [(middle, top + 1.4), (middle, top + 2.6)], closed=False, line=seam))
    paths.append(path("split", [(left + 1.2, split), (left + width - 1.2, split)], closed=False, line=seam))
    if kind in (MOUSE_MIDDLE, WHEEL_UP, WHEEL_DOWN):
        paths.append(rounded("wheel", middle - 1.5, top + 2.8, 3.0, 5.6, 1.4, fill=lit))
    if kind == WHEEL_UP:
        paths.append(path("turn", [(middle, split + 2.2), (middle + 3.2, split + 6.2), (middle - 3.2, split + 6.2)], fill=lit))
    elif kind == WHEEL_DOWN:
        paths.append(path("turn", [(middle, split + 7.0), (middle + 3.2, split + 3.0), (middle - 3.2, split + 3.0)], fill=lit))
    elif kind == MOUSE_SIDE:
        paths.append(rounded("nub", 0.0, split - 3.2, 2.6, 6.4, 1.2, fill=lit))
    return paths


def _choose(state: str, table: list) -> object:
    """A balanced select over a numeric state: `table` is (value, result) in
    rising value order, and the state at one of those values yields its
    result. Any other value yields a neighbour's, which a hidden node never
    draws."""
    if len(table) == 1:
        return table[0][1]
    middle = len(table) // 2
    return {"op": "select", "args": [{"op": "<", "args": [{"state": state}, table[middle][0]]},
                                     _choose(state, table[:middle]), _choose(state, table[middle:])]}


def _within(state: str, values) -> dict:
    """The state is one of `values`: a range test when they run unbroken."""
    values = sorted(values)
    if values == list(range(values[0], values[-1] + 1)):
        return {"op": "&&", "args": [{"op": ">=", "args": [{"state": state}, values[0]]},
                                     {"op": "<=", "args": [{"state": state}, values[-1]]}]}
    return _any(state, tuple(values))


def _chosen_art(doc, ident: str, arts: list, symbol, width) -> dict:
    """One glyph whose art is chosen by binding: `arts` is each
    (symbol, width, draw) it can show, `symbol` and `width` the expressions
    that choose. One node per slot draws whichever the slot's kind names,
    where a node per kind left a slot about twenty hidden glyphs to build,
    style and bind (docs/dev/ui/menu-page-weight.md)."""
    for name, art_width, draw in arts:
        if name not in doc.symbols:
            doc.symbols[name] = _fractions(draw(), art_width)
    node = {"id": ident, "type": "vector",
            "properties": {"display": keyword("none"), "width": em(arts[0][1] / BOX), "height": em(1),
                           "symbol": keyword(arts[0][0])}}
    doc.bind(ident, "symbol", symbol)
    doc.bind(ident, "width", width)
    return node


def key_slot(doc, ident: str, state: str) -> dict:
    """One keyboard or mouse key: `state` is its key state, with
    `state`.glyph and `state`.arrow beside it."""
    doc.state[state] = {"type": "string", "initial": ""}
    doc.state[f"{state}.glyph"] = {"type": "number", "initial": 0}
    doc.state[f"{state}.arrow"] = {"type": "number", "initial": 0}
    kind, arrow = f"{state}.glyph", f"{state}.arrow"
    cap = _cap(doc, f"{ident}-cap", state, "key")
    cap["properties"]["display"] = keyword("none")
    _show(doc, cap, {"op": "&&", "args": [_is(kind, KEYCAP), _is(arrow, 0)]})
    # An arrow key's keycap (a keycap kind with its arrow), or the mouse with
    # its bound button: one node draws whichever the key is.
    arrows = [(d, f"key-arrow-{d}") for d in (1, 2, 3, 4)]
    mice = [(v, f"key-mouse-{v}") for v in (MOUSE_LEFT, MOUSE_RIGHT, MOUSE_MIDDLE, WHEEL_UP, WHEEL_DOWN, MOUSE_SIDE)]
    arts = [(name, BOX, lambda d=d: _arrow(d)) for d, name in arrows] + \
           [(name, MOUSE_W, lambda v=v: _mouse(v)) for v, name in mice]
    keycap = _is(kind, KEYCAP)
    art = _chosen_art(doc, f"{ident}-art", arts,
                      {"op": "select", "args": [keycap, _choose(arrow, arrows), _choose(kind, mice)]},
                      {"op": "select", "args": [keycap, 1.0, round(MOUSE_W / BOX, 4)]})
    _show(doc, art, {"op": "||", "args": [{"op": "&&", "args": [keycap, {"op": "!=", "args": [{"state": arrow}, 0]}]},
                                          _within(kind, [v for v, _ in mice])]})
    # A side button's number stands in the body under the split.
    number_text = _text(f"{ident}-side", 8.5, {"position": keyword("absolute"), "left": length(12.5, "%"), "top": length(46, "%"),
                                                "width": length(75, "%"), "line-height": em(1.25)})
    number_text["properties"]["display"] = keyword("none")
    doc.bind(f"{ident}-side", "text", {"state": state})
    _show(doc, number_text, _is(kind, MOUSE_SIDE))
    art["properties"]["position"] = keyword("relative")
    art["children"] = [number_text]
    return group(ident, {"position": keyword("relative"), "display": keyword("none"), "flex-direction": keyword("row"),
                         "align-items": keyword("center"), "height": em(1), "margin-right": em(GAP), "flex-shrink": number(0)},
                 [cap, art])


def _pad_arts() -> dict:
    """Each controller glyph's width and art by kind."""
    ink = solid(CAP_INK)
    disc = lambda: circle("disc", 11, 11, 10.2, **PLATE)
    arts = {LETTER: (BOX, [disc()])}
    for kind, family, position in ((CROSS, "playstation", "south"), (CIRCLE, "playstation", "east"), (SQUARE, "playstation", "west"),
                                   (TRIANGLE, "playstation", "north"), (SOUTH, "generic", "south"), (EAST, "generic", "east"),
                                   (WEST, "generic", "west"), (NORTH, "generic", "north")):
        arts[kind] = (BOX, face_paths(family, position))
    arts[BUMPER] = (32.0, [rounded("plate", 1, 4.5, 30, 13, 4, top_only=True, **PLATE)])
    arts[TRIGGER] = (24.0, [rounded("plate", 2, 2, 20, 18, 7, top_only=True, **PLATE)])
    arm, reach = 3.6, 10.2
    plus = [(11 - arm, 11 - reach), (11 + arm, 11 - reach), (11 + arm, 11 - arm), (11 + reach, 11 - arm), (11 + reach, 11 + arm),
            (11 + arm, 11 + arm), (11 + arm, 11 + reach), (11 - arm, 11 + reach), (11 - arm, 11 + arm), (11 - reach, 11 + arm),
            (11 - reach, 11 - arm), (11 - arm, 11 - arm)]
    inset = 1.3
    lit = {DPAD_UP: (11 - arm + inset, 11 - reach + inset, 2 * (arm - inset), reach - arm),
           DPAD_DOWN: (11 - arm + inset, 11 + arm - inset, 2 * (arm - inset), reach - arm),
           DPAD_LEFT: (11 - reach + inset, 11 - arm + inset, reach - arm, 2 * (arm - inset)),
           DPAD_RIGHT: (11 + arm - inset, 11 - arm + inset, reach - arm, 2 * (arm - inset))}
    for kind, (x, y, w, h) in lit.items():
        arts[kind] = (BOX, [path("cross", plus, fill=solid(CAP_FILL), line=stroke(CAP_EDGE, EDGE_W)),
                            path("arm", [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], fill=solid(CAP_LIT))])
    arts[STICK] = (BOX, [circle("rim", 11, 11, 10.2, line=stroke(CAP_EDGE, 1.1)), circle("cap", 11, 11, 8.0, **PLATE)])
    bar = stroke(CAP_INK, 1.5)
    arts[MENU] = (BOX, [disc()] + [path(f"bar-{i}", [(6.8, 11 + dy), (15.2, 11 + dy)], closed=False, line=bar)
                                   for i, dy in enumerate((-3.2, 0.0, 3.2))])
    arts[VIEW] = (BOX, [disc(), path("back", [(6.5, 12.6), (6.5, 6.5), (12.6, 6.5), (12.6, 9.4)], closed=False, line=bar),
                        path("back-foot", [(6.5, 12.6), (9.4, 12.6)], closed=False, line=bar),
                        path("front", [(9.4, 9.4), (15.5, 9.4), (15.5, 15.5), (9.4, 15.5)], line=bar)])
    arts[HOME] = (BOX, [disc(), path("roof", [(5.8, 11.4), (11, 6.2), (16.2, 11.4)], closed=False, line=bar),
                        path("walls", [(7.6, 10.2), (7.6, 15.6), (14.4, 15.6), (14.4, 10.2)], closed=False, line=bar)])
    arts[TOUCHPAD] = (32.0, [rounded("plate", 1, 3.5, 30, 15, 3.5, **PLATE), circle("dot", 16, 11, 1.7, fill=ink)])
    arts[PADDLE] = (26.0, [rounded("plate", 1, 3, 24, 16, 5, **PLATE)])
    return arts


def pad_slot(doc, ident: str, state: str) -> dict:
    """One controller button: `state` is its key state, with `state`.glyph
    beside it."""
    doc.state[state] = {"type": "string", "initial": ""}
    doc.state[f"{state}.glyph"] = {"type": "number", "initial": 0}
    kind = f"{state}.glyph"
    kinds = sorted(PAD_WIDTHS)
    art = _chosen_art(doc, f"{ident}-art",
                      [(f"key-pad-{value}", PAD_WIDTHS[value][0], lambda value=value: _pad_arts()[value][1]) for value in kinds],
                      _choose(kind, [(value, f"key-pad-{value}") for value in kinds]),
                      _choose(kind, [(value, round(PAD_WIDTHS[value][0] / BOX, 4)) for value in kinds]))
    _show(doc, art, _within(kind, kinds))
    arts = [art]
    cap = _cap(doc, f"{ident}-cap", state, "button")
    cap["properties"]["display"] = keyword("none")
    _show(doc, cap, _is(kind, BUTTON))
    # The engine's label for the family in use (A, LB, RT, L3, P1) over its glyph.
    name = _text(f"{ident}-name", 11, {"position": keyword("absolute"), "left": length(0), "top": length(0),
                                        "width": length(100, "%"), "display": keyword("none")})
    doc.bind(f"{ident}-name", "text", {"state": state})
    _show(doc, name, _any(kind, LABELLED))
    return group(ident, {"position": keyword("relative"), "display": keyword("none"), "flex-direction": keyword("row"),
                         "align-items": keyword("center"), "height": em(1), "margin-right": em(GAP), "flex-shrink": number(0)},
                 [*arts, cap, name])


PAD_WIDTHS = {kind: (width, None) for kind, (width, _) in _pad_arts().items()}


MENU_BINDS = 3    # keys of each device family an action keeps (idKeyInput::MAX_MENU_BINDS)


def bound_keys(doc, ident: str, state: str, keys: int = MENU_BINDS, pads: int = MENU_BINDS) -> list:
    """The chips of the action whose binding state is `state`: `keys`
    keyboard or mouse keys, then `pads` controller buttons, each shown while
    the action has that many (`state`.keyCount, `state`.padCount)."""
    doc.state[f"{state}.keyCount"] = {"type": "number", "initial": 0}
    doc.state[f"{state}.padCount"] = {"type": "number", "initial": 0}
    chips = []
    for family, count, build in (("key", keys, key_slot), ("pad", pads, pad_slot)):
        for slot in range(count):
            chip = build(doc, f"{ident}-{family}{slot}", f"{state}.{family}{slot}")
            _show(doc, chip, {"op": ">", "args": [{"state": f"{state}.{family}Count"}, slot]}, "flex")
            chips.append(chip)
    if keys and pads:
        chips[keys - 1]["properties"]["margin-right"] = em(GAP + GROUP_GAP)
    return chips


# ----------------------------------------------------------------- prompts

PROMPT_GLYPHS = "prompt.glyphs"     # 0 the keyboard, 1-5 a controller family (RetainedUI_PromptGlyphs)
PROMPT_SWAPPED = "prompt.swapped"   # menus confirm on the east face button
SWAPPED_FACE = {"south": "east", "east": "south"}


def prompt_states(doc) -> None:
    doc.state.setdefault(PROMPT_GLYPHS, {"type": "number", "initial": 0})
    doc.state.setdefault(PROMPT_SWAPPED, {"type": "boolean", "initial": False})


def _face_art(doc, ident: str, family: str, position: str) -> dict:
    return _art(doc, ident, f"prompt-{family}-{position}", BOX, lambda: face_paths(family, position))


def _shoulder_art(doc, ident: str, family: str, side: int, trigger: bool) -> dict:
    """A bumper or trigger with the family's label on it."""
    width = 24.0 if trigger else 32.0
    labels = TRIGGER_LABELS if trigger else SHOULDER_LABELS
    plate = (lambda: [rounded("plate", 2, 2, 20, 18, 7, top_only=True, **PLATE)]) if trigger else \
        (lambda: [rounded("plate", 1, 4.5, 30, 13, 4, top_only=True, **PLATE)])
    art = _art(doc, f"{ident}-plate", f"prompt-{'trigger' if trigger else 'bumper'}", width, plate)
    art["properties"]["display"] = keyword("block")
    name = _text(f"{ident}-name", 11, {"position": keyword("absolute"), "left": length(0), "top": length(0),
                                        "width": length(100, "%")}, key=LABEL_KEYS[labels[family][side]])
    return group(ident, {"position": keyword("relative"), "display": keyword("none"), "height": em(1), "flex-shrink": number(0)},
                 [art, name])


def prompt_glyph(doc, ident: str, *, key_name: str | None = None, face: str | None = None, shoulder: int | None = None,
                 trigger: bool = False, size_dp: float = 20.0) -> dict:
    """The glyph a prompt shows for the device in use: the keyboard's keycap
    named `key_name` (a language key) while prompt.glyphs is 0, else the
    family's face button at `face` (south, east, west, north; south and east
    trade places while prompt.swapped is set), or its `shoulder` bumper (0
    left, 1 right) or, with `trigger`, its trigger. Without `key_name` the
    glyph shows only for a controller."""
    prompt_states(doc)
    parts = []
    if key_name:
        cap = _cap(doc, f"{ident}-key", None, "key", key=key_name)
        parts.append(_show(doc, cap, _is(PROMPT_GLYPHS, 0)))
    for index, family in enumerate(FAMILIES, start=1):
        if face:
            plain = _face_art(doc, f"{ident}-{family}", family, face)
            if face in SWAPPED_FACE:
                swapped = _face_art(doc, f"{ident}-{family}-swapped", family, SWAPPED_FACE[face])
                parts.append(_show(doc, plain, {"op": "&&", "args": [_is(PROMPT_GLYPHS, index),
                                                                     {"op": "!", "args": [{"state": PROMPT_SWAPPED}]}]}))
                parts.append(_show(doc, swapped, {"op": "&&", "args": [_is(PROMPT_GLYPHS, index), {"state": PROMPT_SWAPPED}]}))
            else:
                parts.append(_show(doc, plain, _is(PROMPT_GLYPHS, index)))
        elif shoulder is not None:
            parts.append(_show(doc, _shoulder_art(doc, f"{ident}-{family}", family, shoulder, trigger), _is(PROMPT_GLYPHS, index)))
    return group(ident, {"position": keyword("relative"), "display": keyword("flex"), "flex-direction": keyword("row"),
                         "align-items": keyword("center"), "height": em(1), "font-size": length(size_dp),
                         "flex-shrink": number(0), "pointer-events": keyword("none")}, parts)
