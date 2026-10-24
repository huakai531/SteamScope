# SteamScope UI freeze

Recorded: **2026-10-24 America/Los_Angeles**.

**UI STATUS: FROZEN FOR PORTFOLIO RELEASE**

The owner explicitly accepted Landing, Discover, Player Profile and Messages in the UI Freeze + GitHub Public Release Gate brief. This is visual approval of the current direction, not approval to redistribute every image, publish screenshots, or deploy a service.

## Accepted baseline

Dark gaming-community foundation; Gaming Community + Premium Game Network composition; cool blue accent; persistent desktop sidebar; game imagery, honest avatar fallbacks and compact gaming evidence. Landing V4 composition, current typography and spacing, and the integrated Beautiful UI primitives remain unchanged.

This candidate preserves the accepted layout, typography, navigation, behavior and motion. Only unresolved commercial artwork and isolated illustrative data were replaced with original fictional demo visuals. The original development repository is retained privately.

## Final tokens and behavior

| Role | Current value/source |
| --- | --- |
| Background / panel / surface / elevated | `#0f1012` / `#17181b` / `#1e2024` / `#23252a` |
| Main / secondary / metadata text | `#f5f5f5` / `#a6a7ab` / `#92959e` |
| Accent / accent surface | `#8eb2ff` / `#23334f` |
| Border | White at 8% opacity; input edge `#454951` |
| Success / warning / danger | `#9bcbb0` / `#dec08b` / `#e6a2a5` |
| Font | Segoe UI, system-ui, sans-serif; no downloaded font assets |
| Body | 15px, line-height 1.5; smaller metadata remains scoped |
| Control radius | 8px; component-specific avatar/card geometry retained |
| Focus | Visible 2px accent outline, 2px offset on inputs |
| Motion | 160ms controls; existing Landing preview float/pause/reduced-motion behavior |
| Responsive chat | Two panes on desktop; list/detail navigation below 900px |

Canonical source: `frontend/src/app/globals.css`, `beautiful-ui.css`, `product-polish.css`, and existing scoped page styles. These values describe implementation, not a new token migration.

## Beautiful UI source inventory

Official source: [Beautiful UI](https://beautiful-ui.dev/); [free-item MIT terms](https://beautiful-ui.dev/license), rechecked 2026-10-24. Registry source was installed with shadcn 4.21.0 and adapted. No Pro components or aesthetic dependencies were added in this gate.

| Component | Local source under `frontend/src/components/ui/notchset/` |
| --- | --- |
| Button | `button.tsx` |
| Input | `input.tsx` |
| Textarea | `textarea.tsx` |
| Avatar | `avatar.tsx` |
| Dropdown Menu | `dropdown-menu.tsx` |
| Select | `select.tsx` |
| Segmented Control | `segmented-control.tsx` |
| Empty State | `empty-state.tsx` |
| Dialog | `dialog.tsx` |

Related helpers remain under `frontend/src/lib/beautiful-ui/notchset/`; integration adapters include `ui.tsx`, `choice-select.tsx` and `confirm-dialog.tsx`. Retain `frontend/THIRD_PARTY_NOTICES.md` and source attribution headers. Component licensing does not cover game artwork.

## One final consistency pass

Reviewed Discover density, game-icon/avatar/CTA alignment and empty-state spacing; Profile avatar, gaming identity, statistics and art crops; Messages list width, header, bubble/composer spacing and timestamps. Landing structure was checked without redesign. Desktop, tablet and phone views retain the accepted layout. **No product code or CSS change was necessary.** No repeat design iteration was performed.

Current verification: format, lint, typecheck, **59 unit tests in 12 files**, **36 Playwright tests**, production Turbopack build: all exit 0. The suite covers Landing/Login, Profile/Library/Achievements, Discover/Connections/Notifications, Messages and Privacy. Steam transport was mocked; test database/Redis were isolated. The freeze itself did not rerun backend tests. The later independent candidate did rerun all 313 backend tests; see the validation summary for that separate run.

## Allowed and prohibited work

Allowed before publication: evidenced bug/accessibility repairs and small spacing, alignment, padding, avatar/bubble sizing, typography consistency, responsive overflow, focus or hover corrections. Validate affected behavior and document the reason.

Prohibited without a new owner decision: navigation, palette or page-architecture replacement; new Landing composition; another UI framework/component system; broad Tailwind redesign; aesthetic dependency additions. Phase 7 remains outside this task.

## Limits and screenshots

- Target: **1440 × 900 content viewport, device scale 1, 100% browser zoom**. Additional responsive checks use 768px and 390px.
- Small timestamp/metadata text is intentionally retained; this pass is not a complete WCAG conformance audit.
- Account avatars use initials when the authorized DTO has no image; no invented Steam avatar is substituted.
- Original fictional SVG demo art is MIT-licensed with the project; no commercial game artwork is bundled.
- Screenshots use declared isolated demo data, not real platform adoption. The candidate screenshot set is reviewed separately and disclosed as synthetic.
- Candidate validation and Docker startup are documented in the public validation summary; the original development stack is separate.

See [validation summary](../development/VALIDATION.md) and [screenshot index](SCREENSHOT_INDEX.md).
