<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: Built-In UI Theme Catalog Extension

Companion specification for the `ux` requirements that define the four
non-brand built-in themes added to the AudioMancer theme catalog: Midnight
Studio, Ember Night, Nordic Slate, and Ink and Paper.

- Requirements: the `ux` set covering the built-in theme catalog
  (`midnight_studio`, `ember_night`, `nordic_slate`, `ink_and_paper`).
- Affected files:
  - `04_Software/AudioMancer/src/audiomancer/services/ui_theme_service.py`
  - `04_Software/AudioMancer/tests/test_ui_theme_service.py`

## Behavior

### The gap

Before this change the catalog held seven built-in themes: `classic_light`,
`warm_reading`, `high_contrast`, `default_dark`, `dark_contrast`,
`audiomancer_dark` (the default), and `audiomancer_parchment`. Four registers
were unrepresented:

- **No warm dark theme.** `warm_reading` is the only warm palette and it is
  light-on-light, so an operator working at night either accepts the cool
  brand teal or a neutral grey.
- **No cool-neutral dark theme.** `audiomancer_dark` carries brand identity;
  `default_dark` is close to neutral but keeps a generic blue accent and no
  distinct character.
- **No low-contrast, desaturated theme.** `dark_contrast` is deliberately
  maximal; nothing sits at the calm end for multi-hour block editing.
- **No near-monochrome light theme.** `audiomancer_parchment` is warm plus
  gold; `classic_light` is a plain system light. Neither is a restrained
  typographic surface where colour appears only where it carries meaning.

### Catalog placement

The four themes are appended to `_BUILT_IN_THEMES` after
`audiomancer_parchment`. Placement matters because `built_in_themes()` order is
the Settings-page combo order (`settings_page.py` iterates the catalog to fill
`_theme_combo`) and because `_classic_light_theme()` reads index `0`. Appending
keeps both contracts intact: `classic_light` stays first and no existing theme
changes position.

All four carry `built_in = True`, `schema_version = THEME_SCHEMA_VERSION`, and
the default font payload for both `font` and `text_font`, so the operator's
font-size and scale preferences behave exactly as they do for every existing
built-in theme.

### Nothing else changes

`default_theme_id()` still returns `audiomancer_dark`. The theme schema, the
ten `THEME_COLOR_ROLES` names, validation, import/export, duplication, and the
custom-theme collection are untouched. No settings migration is needed: a
persisted `selected_theme_id` naming one of the new ids simply resolves, and
any unknown id already self-heals to the default.

### Contrast basis

Each palette was checked with the WCAG 2.1 relative-luminance formula against
its own surfaces. The targets applied were 4.5:1 for `text_primary` on both
backgrounds, 4.5:1 for `text_muted` on `panel_background`, 4.5:1 for
`window_background` used as label text on an `accent` fill (the primary-button
pattern), and 3.0:1 for `accent`, `warning`, `success`, and `danger` on
`panel_background`. `disabled` is intentionally exempt from a text minimum: it
signals unavailability and must read as recessed.

Nord's canonical aurora red `#BF616A` reaches only 2.46:1 on `#3B4252`, so
Nordic Slate uses a lightened `#D4838C` (3.56:1) instead. This is the one
deliberate departure from the palette the theme is modelled on.

## Data Structures

### Midnight Studio — `midnight_studio`, "Midnight Studio"

A cool navy-indigo dark theme with a violet accent, deliberately outside the
brand teal so operators who want a dark UI without AudioMancer branding have
one. Register: audio workstation.

| Role | Value |
| --- | --- |
| `window_background` | `#12141C` |
| `panel_background` | `#1B1F2B` |
| `text_primary` | `#E6E9F2` |
| `text_muted` | `#A0A7BC` |
| `accent` | `#7C6CFF` |
| `border` | `#303648` |
| `warning` | `#E3B341` |
| `success` | `#4CC38A` |
| `danger` | `#E5646E` |
| `disabled` | `#6A7185` |

### Ember Night — `ember_night`, "Ember Night"

A warm charcoal-brown dark theme with an amber accent, low blue emission, for
night sessions. `success` is shifted toward olive (`#8FB25A`) rather than a
cool green so the status row stays inside the warm palette.

| Role | Value |
| --- | --- |
| `window_background` | `#1A1512` |
| `panel_background` | `#241D18` |
| `text_primary` | `#F2E7DA` |
| `text_muted` | `#B7A392` |
| `accent` | `#FF9F45` |
| `border` | `#40342B` |
| `warning` | `#E8B14A` |
| `success` | `#8FB25A` |
| `danger` | `#E0685A` |
| `disabled` | `#7A6A5C` |

### Nordic Slate — `nordic_slate`, "Nordic Slate"

A desaturated slate-blue dark theme at moderate contrast, modelled on the Nord
palette. The calm counterpart to `dark_contrast`, intended for long editing
sessions in the speech-block views.

| Role | Value |
| --- | --- |
| `window_background` | `#2E3440` |
| `panel_background` | `#3B4252` |
| `text_primary` | `#ECEFF4` |
| `text_muted` | `#B4BCCA` |
| `accent` | `#88C0D0` |
| `border` | `#4C566A` |
| `warning` | `#EBCB8B` |
| `success` | `#A3BE8C` |
| `danger` | `#D4838C` |
| `disabled` | `#7B8494` |

### Ink and Paper — `ink_and_paper`, "Ink and Paper"

A near-monochrome light theme on a neutral-warm paper ground with a deep
slate-ink accent. Colour appears only where it carries status meaning; the rest
is typographic grey. Complements `audiomancer_parchment`, which is warm and
gold.

| Role | Value |
| --- | --- |
| `window_background` | `#EFEFEC` |
| `panel_background` | `#FFFFFF` |
| `text_primary` | `#1A1A18` |
| `text_muted` | `#5C5C57` |
| `accent` | `#33475B` |
| `border` | `#DCDCD6` |
| `warning` | `#8A6100` |
| `success` | `#2C6E49` |
| `danger` | `#9B2C2C` |
| `disabled` | `#A8A8A2` |

## Examples

Measured contrast ratios for the four constrained pairs per theme:

| Theme | `text_primary` on `panel_background` | `text_muted` on `panel_background` | `window_background` on `accent` | `danger` on `panel_background` |
| --- | --- | --- | --- | --- |
| Midnight Studio | 13.54 | 6.85 | 4.77 | 4.99 |
| Ember Night | 13.62 | 6.86 | 8.88 | 4.98 |
| Nordic Slate | 8.73 | 5.26 | 6.24 | 3.56 |
| Ink and Paper | 17.43 | 6.72 | 8.31 | 7.53 |

| Input | Expected result |
| --- | --- |
| `built_in_themes()` | eleven payloads; ids in order `classic_light`, `warm_reading`, `high_contrast`, `default_dark`, `dark_contrast`, `audiomancer_dark`, `audiomancer_parchment`, `midnight_studio`, `ember_night`, `nordic_slate`, `ink_and_paper` |
| `theme_by_id("nordic_slate", [])` | the Nordic Slate payload with `built_in` `True` |
| `theme_by_id("missing_theme", [])` | unchanged: the `audiomancer_dark` payload |
| `export_theme_payload(<Ember Night>)` | a custom payload keeping the ten colour roles, `built_in` `False` |
| `import_theme_payload(<exported Ember Night>, [])` | `theme_id` `ember_night_2`, `built_in` `False` |
| a custom theme claiming `theme_id` `ink_and_paper` | dropped by `normalize_theme_collection`, as for every other built-in id |

## Acceptance

- [ ] `built_in_themes()` returns the seven pre-existing themes in their original order, followed by `midnight_studio`, `ember_night`, `nordic_slate`, `ink_and_paper`.
- [ ] Each new theme validates under `validate_theme_payload(..., allow_built_in=True)` and reports `built_in` `True`.
- [ ] Each new theme's ten colour roles match the tables above exactly, in uppercase `#RRGGBB` form.
- [ ] Each new theme uses the default font payload for both `font` and `text_font`.
- [ ] `default_theme_id()` still returns `audiomancer_dark`, and an unresolved theme id still falls back to it.
- [ ] `_classic_light_theme()` still resolves `classic_light`, so omitted custom colour roles keep falling back to the classic light values.
- [ ] The Settings-page theme combo lists all eleven built-in themes without any change to `settings_page.py`.
