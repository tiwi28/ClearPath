---
name: ClearPath
description: Toronto trip planning for people with mobility limits, built from the curb-cut warning plate.
colors:
  asphalt: "#262626"
  asphalt-raised: "#3a3a38"
  dome-yellow: "#f5c400"
  dome-shadow: "#d9ac00"
  dome-wash: "#fff8d6"
  curb-concrete: "#d6d3cc"
  curb-light: "#ebe9e4"
  paper: "#ffffff"
  ink: "#1a1a1a"
  muted-stone: "#5a5852"
  edge-stone: "#85827a"
  hairline: "#dcd9d2"
  route-blue: "#1d4fa3"
  stairs-red: "#b42318"
  win-green: "#17603d"
  barrier-amber: "#c25e00"
typography:
  display:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  figure:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  title:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 700
    lineHeight: 1.5
  body:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 700
    lineHeight: 1.5
rounded:
  chip: "6px"
  field: "8px"
  control: "10px"
  card: "12px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "16px"
  lg: "20px"
  gutter: "28px"
components:
  button-primary:
    backgroundColor: "{colors.asphalt}"
    textColor: "{colors.paper}"
    typography: "{typography.title}"
    rounded: "{rounded.control}"
    padding: "13px 18px"
    height: "52px"
  button-primary-hover:
    backgroundColor: "#000000"
    textColor: "{colors.dome-yellow}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "13px 18px"
    height: "52px"
  button-secondary-hover:
    backgroundColor: "{colors.curb-light}"
  input-address:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "11px 14px"
    height: "48px"
  choice-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "14px 16px"
  choice-card-selected:
    backgroundColor: "{colors.dome-wash}"
  option-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "16px 18px"
  option-card-selected:
    backgroundColor: "{colors.dome-wash}"
  option-card-typical:
    backgroundColor: "{colors.curb-light}"
  warning-chip:
    backgroundColor: "{colors.asphalt}"
    textColor: "{colors.dome-yellow}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "4px 10px"
  blocker-chip:
    backgroundColor: "{colors.stairs-red}"
    textColor: "{colors.paper}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "3px 10px"
  rail-step-current:
    backgroundColor: "{colors.dome-yellow}"
    textColor: "{colors.asphalt}"
    rounded: "{rounded.field}"
    size: "40px"
  map-legend:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "14px 16px"
  map-layer-panel:
    backgroundColor: "{colors.asphalt}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
---

# Design System: ClearPath

## Overview

**Creative North Star: "The Curb-Cut Plate"**

ClearPath is built from the yellow truncated-dome plate set into every Toronto curb cut: the one surface wheelchair and cane users read with wheels and feet. Asphalt carries the chrome, safety yellow carries attention and the dome texture, curb concrete is the ground, and a white working panel holds the decision. Everything is large, heavy and high-contrast, because every user may have low vision, tremor or fatigue.

The shell is three columns on desktop: an asphalt step rail, a white planner panel opened by a yellow dome band that states the step's question, and a desaturated map filling the rest. Selection is shown the way paving shows a hazard: a heavy asphalt frame on a pale-yellow field. Warnings are asphalt chips with yellow type, the plate's own colour pairing. Route blue appears only where it means "the route you chose".

The system rejects the floating-white-panel map app with a blue line and nothing else to say. The typical route's cost (stairs, unconfirmed ends, barrier exposure) is always stamped next to the route that avoids it.

**Key Characteristics:**
- Asphalt, dome yellow and curb concrete as the three material colours; white only for the working panel and cards.
- The dome grid (yellow field, darker yellow dots on a 22px pitch) as the signature texture, used on the band and the brand mark only.
- One typeface, Atkinson Hyperlegible Next, at 400 / 700 / 800; 800 for headings, numerals and buttons.
- Thick 2-3px asphalt frames for selection and the legend; no decorative elevation inside the panel.
- 48-52px hit targets on every primary control.

## Colors

A material palette from the street: asphalt, warning-plate yellow, concrete, with a reserved blue for the chosen route and a red for stairs.

### Primary
- **Dome Yellow**: the attention signal. Fills the step band, the current rail step, the forecast-day select, the endpoint marker ring, and is the type colour on asphalt warning chips and the primary button hover. Never used as text on white.
- **Dome Shadow**: only the dots of the dome grid on top of Dome Yellow.
- **Dome Wash**: the selected-state field behind asphalt frames (profile cards, toggles, route cards) and the hover/active row in address suggestions.

### Secondary
- **Route Blue**: the person's chosen route line on the map (6px with a 10px white casing), the start marker, links, link-buttons, caret and the global focus outline. Reserved; do not use it as a general accent.

### Tertiary
- **Stairs Red**: stairs on the map, elevator outages, blocker chips (white text), field errors.
- **Barrier Amber**: unconfirmed segments on the map (dashed), the route's barrier-exposure fill bar, and the 0.3 stop of the risk ramp.
- **Win Green**: the "Avoids 2 sets of stairs" line on the accessible route card and the OK badge text.

### Neutral
- **Asphalt**: rail, primary button, warning chips, map layer panel, legend frame, selected-card frame, developer `pre` blocks.
- **Asphalt Raised**: hover fill for rail steps.
- **Curb Concrete**: page and map-panel ground.
- **Curb Light**: typical-route card, walking-leg pills, secondary-button hover, developer drawer ground.
- **Paper**: planner panel, cards, inputs, legend.
- **Ink**: body text.
- **Muted Stone**: secondary text, the typical route line on the map, distances and captions.
- **Edge Stone**: input borders and the hover border on cards.
- **Hairline**: 1-2px resting borders on cards and dividers.

### Named Rules
**The Plate Pairing Rule.** Warnings are asphalt with yellow type; selection is an asphalt frame on Dome Wash. Yellow is only ever read against asphalt or as a fill under asphalt type.

**The Your-Route Rule.** Route Blue belongs to the chosen route. The typical route is Muted Stone, dashed when not selected; stairs are red; unconfirmed is amber.

**The Risk Ramp Rule.** Sidewalk-barrier risk is a single warm ramp from Dome Wash through `#f2d36b` and Barrier Amber to `#5a1a00` (stops at 0.02 / 0.1 / 0.3 / 0.6), with fill opacity rising 0.04 to 0.5. The legend ramp and map hexes share the same stops.

## Typography

**Display Font:** Atkinson Hyperlegible Next (with Atkinson Hyperlegible, system-ui)
**Body Font:** Atkinson Hyperlegible Next
**Label/Mono Font:** same family; developer JSON uses the browser monospace at 12px

**Character:** One low-vision legibility face carrying everything, made assertive by weight: 800 for questions, numerals and buttons, 700 for titles and labels, 400 for explanation.

### Hierarchy
- **Display** (800, 1.875rem, 1.2, -0.015em; 1.625rem under 760px): the step question in the yellow band, one per screen.
- **Figure** (800, 2rem, 1, -0.02em, tabular): trip durations on option cards, right-aligned with a 0.9375rem muted distance beneath.
- **Title** (700, 1.0625rem): card titles, trip summary; buttons use the same size at 800.
- **Body** (400, 1rem, 1.5): intro copy capped at 46ch, directions, notes. Secondary detail text drops to 0.9375rem in Muted Stone.
- **Label** (700, 0.875rem): chips, badges, leg pills, legend text, field labels. Sentence case; no uppercase tracking.

### Named Rules
**The Heavy Numeral Rule.** Numbers the person decides on (minutes, step numbers) are 800 weight with tabular figures.

## Layout

Desktop is a fixed three-column grid: 88px rail, a 380-440px planner panel, and the map at `minmax(0, 1fr)`, all at full `100dvh`. The panel scrolls; the developer drawer sits at its foot via `margin-top: auto`. The panel gutter is 28px; step content stacks at 16px; option and profile lists at 8-10px; inline groups at 6px.

Under 760px the rail becomes a sticky horizontal top bar (brand mark left, numbered steps right), the panel dissolves into the page column, the map follows the step content at 60dvh, and the developer drawer closes the page. Gutters drop to 16px. Under 420px the rail labels and wordmark become screen-reader-only, leaving the numbered squares.

Back/primary action pairs use a 1fr / 2fr grid so the forward action dominates.

## Elevation & Depth

The panel is flat; depth there comes from frame weight, not shadow. Selected cards add a `0 0 0 1-2px` asphalt spread ring to their 2px border, reading as a heavier frame rather than a lift. Real shadows appear only on things that float over the map or a field.

### Shadow Vocabulary
- **Map overlay** (`box-shadow: 0 8px 20px rgb(38 38 38 / .22)`): layer panel and legend over the map.
- **Suggestion list** (`box-shadow: 0 10px 24px rgb(38 38 38 / .18)`): address autocomplete dropdown.
- **Map marker** (`box-shadow: 0 2px 6px rgb(0 0 0 / .35)`): A/B endpoint markers.

### Named Rules
**The Frame-Not-Float Rule.** Inside the panel, emphasis is a thicker asphalt frame. Shadows are reserved for elements layered over the map or another control.

## Shapes

Gently rounded, never soft: 6px for chips and badges, 8px for fields, the rail number squares and notices, 10px for buttons, choice cards and map overlays, 12px for route cards. Transit legs are full pills. Markers, the brand mark and status dots are circles. Borders are structural and heavy: 2px on cards and inputs at rest, 3px asphalt on the legend. The disclosure marker is a CSS chevron drawn from two borders, rotating 90 degrees on open.

## Components

### Buttons
- **Shape:** gently rounded (10px), minimum height 52px.
- **Primary:** asphalt fill, white 800-weight type at 1.0625rem, full width or the 2fr column at the step's foot.
- **Hover / Focus:** hover goes to black with yellow type. Focus is the global 3px Route Blue outline at 2px offset; on asphalt surfaces the outline switches to Dome Yellow.
- **Secondary:** paper fill, 2px asphalt border; hover to Curb Light.
- **Link button:** Route Blue, 700, 2px underline at 4px offset; hover turns ink with a yellow underline.

### Chips
- **Warning chip:** asphalt with yellow type, 6px radius, 700 weight. Used for "not confirmed free of stairs" and the typical route's stairs cost.
- **Blocker chip:** Stairs Red with white type. **OK badge:** pale green with Win Green type.
- **Leg pills:** 2px border in the TTC line colour on paper for rides; borderless Curb Light at 400 for walks.

### Cards / Containers
- **Choice cards (profiles, toggles):** 10px radius, 2px Hairline border, native radio/checkbox at 22px with asphalt accent. Checked: 2px asphalt border plus 1px ring on Dome Wash.
- **Route option cards:** 12px radius, 16px 18px padding, title left and heavy figure right. Selected: asphalt border plus 2px ring on Dome Wash. The typical route stays Curb Light even when selected.
- **Barrier exposure bar:** 10px track in Curb Light with a fine Curb Concrete dot texture; Barrier Amber fill animating width over 0.5s `cubic-bezier(.22, 1, .36, 1)`.

### Inputs / Fields
- **Style:** 48px min height, 2px Edge Stone border, 8px radius, paper fill, 700-weight label above.
- **Focus:** border goes asphalt with a 3px Dome Yellow outline at 0 offset.
- **Error:** 0.875rem Stairs Red line beneath.

### Navigation
- **Step rail:** asphalt column, numbered 40px squares with 2px borders and 800 numerals, label beneath. Current: yellow fill, asphalt numeral. Done: light border, white numeral. Unreachable: dimmed border and text. Hover on reachable steps: Asphalt Raised fill.

### Dome Band (signature)
The yellow header of the panel: a 44px strip of dome grid over clear yellow carrying the step question in Display type. While routes load, a column of asphalt domes steps across the grid (`steps(40)` over 2s); under reduced motion it becomes a static 25% asphalt overlay.

### Map
Raster tiles desaturated (-0.85 saturation, -0.1 contrast) so the overlay colours carry meaning. The asphalt layer panel sits top-left with yellow checkboxes, a yellow day select and a yellow disclosure chevron; the white legend with a 3px asphalt frame sits bottom-left. Endpoints are 32px circles: A asphalt with a yellow ring, B Route Blue with a white ring.

## Do's and Don'ts

### Do:
- **Do** state each step as one question in the yellow dome band, 800 weight.
- **Do** mark selection with a 2px asphalt border plus ring on Dome Wash.
- **Do** put warnings in asphalt chips with Dome Yellow type, and blockers in Stairs Red with white type.
- **Do** keep primary controls at 48-52px tall and foot each step with a full-width asphalt action.
- **Do** switch focus outlines to Dome Yellow on asphalt surfaces; keep Route Blue elsewhere.
- **Do** show the typical route's cost on its own card, on Curb Light.

### Don't:
- **Don't** use Route Blue for anything but the chosen route, links and focus.
- **Don't** set Dome Yellow text on white or Curb surfaces; it fails contrast.
- **Don't** spread the dome grid beyond the band and the brand mark; it is the decision point, not wallpaper.
- **Don't** add resting shadows to panel cards; use frame weight.
- **Don't** introduce a second typeface or weights outside 400 / 700 / 800.
