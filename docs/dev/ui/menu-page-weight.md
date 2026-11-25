# Menu page weight, a seventh retained UI round

A seventh round on 25 November 2026 measured what the retained menus still
cost after the [menu transitions](menu-transitions.md) round of 22 November:
what a page weighs to load and hold, what a tab change costs on an open page,
and what a page costs while it slides in. Options had grown with the settings
tree's audit and the binding rows' third key of each family, and it was the
outlier on every count.

## What the menus cost

`openq4-retained-ui-benchmark --load` on every Prey document, and
`--screen`, `--transition` and `--event` on the pages that move (`builddir-perf`,
debugoptimized, a machine shared with other sessions' builds and clients):

- **Options weighed as much as every other page together.** 9,036 nodes,
  12,033 vector paths and 5,357 bindings in 11 MB of source; 114 MB for the
  validated document and 135 MB more for its view. MultiPrey, the next
  largest, has 2,082 nodes and 235 paths.
- **Most of it was hidden key glyphs.** A binding row is 132 nodes: each of
  its six chips carried one vector per glyph it might show (four arrow keys
  and six mouse buttons in a key slot, 21 controller glyphs in a pad slot),
  each hidden by a `display` binding until its kind matched. Those were
  5,000 of the page's nodes, 4,920 of its bindings and, with each symbol's
  paths copied into each node, 10,200 of its paths.
- **A tab change laid the page out twice.** The focus moves into the new
  tab, and the focused list's value text animates its colour. A list's value
  text counted as a node the list paints, so that colour started a new
  presentation pass, all 86 lists repainted (their popups' placement,
  inheritance and filters) and the page laid out again in the next frame: 12
  ms of CPU over the four frames after a top-tab change, 9 ms of it layout.
- **A sliding page re-read what takes input on every frame.** Input
  eligibility (each branch's `display` and `pointer-events`) was cached per
  state and motion revision; a page growing out of the bottom bar changes
  the motion every frame, though only the clip boxes' `left` and `top` move.
  Every slider also formatted and wrote its fill, thumb and value again.
  Options opened at 3.1 ms a frame, MultiPrey at 1.8 ms.
- **Options often loaded in the frame that opened it.** The title prepares
  the pages it leads to while it rests, but the warm-up declared itself done
  as soon as it had found every lead either ready or still parsing. Options
  has the slowest parse, so whenever the title began resting before it
  landed (four of five engine runs here) its view was built in the click
  frame: 191 to 466 ms.

Every page at rest stays under 0.2 ms a frame, as the earlier rounds left
them; Load Game, Save Game, Credits, the message box and the multiplayer
Escape card had nothing comparable.

## What changed

- **A vector's `symbol` is a bindable property.** A vector node may name its
  art with a `symbol` property (a keyword), and a binding may switch it among
  the document's symbols: a literal ID or a `select` of them, so the document
  names every art it can draw. Timelines and presentation aliases may not
  write it. The validated model keeps the symbol table, shared by copies;
  the runtime installs the new paths when the binding changes
  (`VectorElement::SetPaths`) and draws them afresh, never from a replayed
  frame ([document format](document-format.md)).
- **One art node per chip.** `tools/ui/retained_key_glyphs.py` gives each key
  or pad slot a single vector whose `symbol` and `width` follow the slot's
  glyph kind through balanced `select` trees, with the mouse side button's
  number inside it. A chip is 6 nodes instead of 15 or 26 and a binding row
  45 instead of 132; the page draws what it drew.
- **A list's value text paints only its text.** `ValueControlView::PaintsNode`
  counts the value text's `text` alone; the popup's subtree and the opacity
  ancestors its filter reads count as before. A colour, display or opacity on
  the value text no longer repaints every list.
- **Input eligibility follows its own stamp.** `Motion::EligibilityRevision`
  moves only with a write that can change a `display` or `pointer-events`
  value (a sample, a play, a cancel, a reduced-motion jump, an external write,
  a reset, a restore or a rollback); the runtime re-reads eligibility on it
  and the state revision, so a page sliding or fading reads it once.
- **A slider repaints only what changed.** Its value, fill extent and thumb
  position are kept with the presentation pass that painted them, as a
  closed list's readback is; the same three in the same pass are left as
  painted.
- **A page's authored values are built with its model.** `Document::Load`
  builds the map of every node's authored values that a motion starts from
  (`DocumentModel::authoredValues`), on the parse worker for a prefetched
  page, and `Motion::Reset` shares it instead of building its own in the
  view's load.
- **The warm-up waits for a lead still parsing.** `WarmRetainedPages` stays
  open while a page the shown page leads to is still parsing on the workers,
  and loads it ahead once its parse lands.
- **Measurement.** `RuntimeStatistics::choiceRepaints` counts the lists a
  frame repainted. `--event` takes setup events before the repeated one
  (`--event settings.rui onActivate,onTabNext`), so tab changes are measured
  on the open page, and reports the four frames after each event: their CPU,
  layout, paths compiled and list repaints.

## Results

Best of three interleaved runs (`.tmp/rui-round7/ab.py`): HEAD's runtime with
HEAD's Options, this round's runtime with HEAD's Options, and this round's
runtime with the regenerated page.

| Measure | HEAD | New runtime | New runtime and page |
| --- | ---: | ---: | ---: |
| Options opening, frame p50 | 3.14 ms | 1.47 ms | 1.46 ms |
| Options opening, layout p50 | 1.89 ms | 0.53 ms | 0.49 ms |
| Options leaving, frame p50 | 3.19 ms | 1.37 ms | 1.31 ms |
| MultiPrey opening, frame p50 | 1.83 ms | 0.83 ms | |
| Top-tab change, event | 2.56 ms | 2.94 ms | 2.08 ms |
| Top-tab change, four frames after it | 12.01 ms | 6.27 ms | 4.47 ms |
| Top-tab change, layout in those frames | 9.19 ms | 3.30 ms | 2.45 ms |
| Side-tab change, event and four frames | 2.86 ms | 3.03 ms | 2.00 ms |
| Options nodes / paths / bindings | 9,036 / 12,033 / 5,357 | | 5,450 / 1,822 / 2,403 |
| Options document and view held | 249 MB | 249 MB | 165 MB |
| Options view build | 192 ms | 194 ms | 149 ms |

Load Game, Save Game and Credits open within 0.05 ms of before. The view
build moved the authored values onto the parse worker; its other parts
(element creation, inline properties, the first presentation pass) remain
spread across the page's nodes, and scale with them.

In the engine (OpenGL, a 1280x720 window, a machine at full load from other
sessions), the title now loads Options ahead while it rests (103 ms) and
compiles its artwork on the workers, so opening it no longer builds its view.
Every Controls tab drew the same glyphs with the regenerated page as before
(keyboard keys, arrow keys, mouse buttons, triggers, bumpers, the d-pad,
sticks, paddles and the view button, with keyboard and controller prompts),
and the Options, MultiPrey and Load Game walks set a slider, opened and closed
a list and changed tabs with no refused binding or operation.

## Found, not fixed

- **A tab's first showing compiles its artwork** (about 50 paths, a few ms)
  in the frame that shows it; the warm-up prepares only the tab a page
  opens on.
- **The view build is still one main-thread step** (about 100 to 150 ms for
  Options while the title rests).
- **A document holds its source twice:** the loaded text and its snapshot
  identity, which embeds the whole source (`Document::SnapshotIdentity`).
- **The generated documents are pretty-printed**, about 40% of their bytes
  whitespace; a pack-time compact form would cut the workers' parse by about
  as much.

## Evidence, 25 November 2026

The kit is in `.tmp/rui-round7/`: `ab.py` (the interleaved A/B, with
`bench-base.exe` built from HEAD's runtime sources), `ab_events.py`,
`census.py`, `tree.py` and `row.py` (what a document's nodes and bindings
are), `collapse.py` (the experiment that sized the glyph change before it was
made), `render_one.py` (one generated document to a file), the sampler
profiles (`load-samples.json`, `tabnext-samples.json`, `trans-samples.json`),
`run.ps1` with `walk.cfg` and `walk2.cfg` (windowed engine runs, the page
under test mounted through `fs_devpath`) and their logs and captures.

Tests: the native retained UI and value-runtime tests, including the new
`CheckBoundSymbol` (`RetainedUiTest.cpp`: the bound art draws, switches both
ways, is never replayed stale, and six malformed documents are refused) and
`ValueColourKeepsPaint` (`UiValueRuntimeTest.cpp`, which fails with HEAD's
list view), and the 81 retained UI and HUD tests in the MSVC environment.
Three fail as they do at HEAD: `openq4-ui-legacy-observation` and
`openq4-ui-sound-recovery` (their stubs do not compile) and
`openq4-ui-value-runtime` ("an open list keeps the full pass every frame",
recorded in the transitions round; every other check passes). The native
`openq4-bitmsg-test` does not build at HEAD.
