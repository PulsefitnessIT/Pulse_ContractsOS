# Pulse Fitness branded staff platform — implementation notes

**Source assets (supplied 5 November 2026)**
- `Style Guidelines.pdf` (one-page Pulse Fitness UI style guide)
- `Pulse Fitness Brand Guidelines.pdf` (2022 corporate guide, version 1)
- `Fonts and logo(1).zip` (official logo artwork and licensed typefaces)

## Design choices

Use the dedicated Pulse Fitness UI style guide for **application chrome and controls**:

| Token | Value | Use |
| --- | --- | --- |
| Core Blue | `#19CDFF` | Primary actions, active tabs, invoice-drop borders, focus rings |
| Soft Black | `#1B1C1D` | Top bar, major text, print masthead |
| Onyx | `#393E41` | Secondary dark surfaces |
| Slate | `#6E7476` | Subheadings / supporting copy |
| Silver | `#E0E0E0` | Dividers, borders |

The older corporate Brand Guidelines (2022) specify Pantone 2985C
and `#66CCFF` as a corporate print/digital colour, while the
separate supplied UI guide specifies `#19CDFF`. This implementation
uses the **UI guide's values for interactive controls** without editing
the supplied master brand signature artwork.

## Official logo and icon

- `app/static/brand/pulse-fitness-reverse.svg` uses the exact three
  path geometries of the supplied original
  `Brand Logo/Brand Logo/Primary/PulseFitness_Reverse.svg`.
  It appears on a **dark background** per the corporate master
  brand guidelines. Its paths are protected by geometry-fingerprint tests.
- `app/static/brand/pulse-fitness-blip.svg` uses the original supplied
  circular blip motif for favicon/vector PWA identity.
- The signature is not redrawn using fonts or CSS; preserve its clearspace.
- Existing PNG PWA icons will need a separate branded binary-asset update
  before public install branding can be certified end-to-end.

## Typography and licensing

The corporate guide uses **MaaxRounded** for prominent headings
and **Proxima Nova** for supporting content. The standalone UI
guide shows Proxima Nova for UI typography. The app uses local
`MaaxRounded` for headings and local `Proxima Nova` for body
text, with accessible Arial/Segoe UI fallbacks. **No proprietary
font binaries** have been pushed to the public GitHub repository;
if Pulse wishes to bundle them in a protected deployment, licensing
and private delivery must be checked first.

## User interface

- Official logo and authentic staff platform masthead
- Service & Aftersales instead of fictional/inert "Memberships/CRM" tabs
- Responsive module navigation, cards, reports and forms
- Accessible focus outlines; reduced-motion styling
- SmartQuote stage flow: Drop PDFs → auto-match exact Master SKUs
  → review unmatched codes → price and approve
- Distinctive PDF invoice drop zone and correct automatic-match copy
- Branded internal A4 print layout retaining the
  **INTERNAL DRAFT — NOT AUTHORISED FOR CUSTOMER ISSUE** limitation
- Branded private-pilot sign-in page and PWA theme colour

The overall brand implementation does not approve commercial maintenance
rates or activate any customer quote issuance.

## Verification

Run the source validation workflow, including
`tests/test_pulse_branding.py`, coordinator Node UI tests, and
the full synthetic Python quote regression suite.

Before release, validate screenshots in a real deployed pilot in
desktop and mobile browsers, ensure the contracted font files may
legally be distributed by the chosen deployment mechanism, and update
any remaining old PNG install icons and customer-facing contract PDFs
with approved branding.
