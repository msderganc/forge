# Web design references (design skill)

Use this catalog when **design** (or later implement) is shaping a **website, landing page, marketing site, or web/app UI**. Skip for CLI-only, API-only, or infra work.

Canonical anti-slop companion: [`templates/uncodixfy-contract.md`](uncodixfy-contract.md) and [Uncodixfy](https://github.com/cyxzdev/Uncodixfy) (`/uncodixfy` when installed). Galleries are for **looking at real work**. Uncodixfy is for **not emitting generic AI UI** when you generate screens.

## When this applies

Activate when any of these are true:

- Scope layer includes **Frontend**
- The ask is a site, landing, marketing page, dashboard, or product chrome
- Studio visual gates are in play
- Solution candidates include layout, type, motion, or component choices

Do **not** paste this whole list into the user chat. Pick **2–4 sources** from the routing table, open them (browser tools when available), and record what you actually looked at.

## How to look

1. Read this file and [`templates/uncodixfy-contract.md`](uncodixfy-contract.md).
2. Choose sources with the routing table — match the **job** (landing vs product chrome vs motion vs one section).
3. Open the live galleries. Capture **3–5 specific references** (page URL or named example), not a vibe.
4. Extract patterns: layout, type, color, hierarchy, motion, section mix. Do not clone a winner.
5. Run Uncodixfy against anything you would generate: if a pattern is default AI UI (glass shells, pill overload, hero-in-dashboard, decorative eyebrows), drop it even if a gallery featured it.
6. Write `web-references.md` in session memory (see below). Carry the same list into the design spec when a spec is required.

**Marketing / landing** may be more expressive (awards, motion, editorial). **App / dashboard / settings chrome** stays Uncodixfy-normal (Linear, Raycast, Stripe, GitHub — functional, not theatrical). Component kits (Aceternity, Magic UI, shadcn blocks) are starters: Uncodixfy them before recommending them as the look.

## Routing (pick a few)

| If you are designing… | Look here first |
|----------------------|-----------------|
| Overall visual direction, experimental or premium sites | Awwwards, The FWA, CSS Design Awards, CSS Winner |
| Marketing / landing page (full page) | Godly, Land-book, Lapa Ninja, One Page Love, Siteinspire |
| SaaS marketing (pricing, careers, product pages) | SaaS Landing Page, Saaspo, Landing.Gallery, A1 |
| Quiet, editorial, independent, or luxury | Minimal Gallery, Httpster, Siteinspire, SeeSaw |
| Dark / cinematic / high-end experiences | Refs.Gallery, The FWA, Awwwards |
| Motion, scroll, hover, 3D | Motion Sites, landing.love, Hoverstat.es |
| React / Tailwind / shadcn building blocks | shadcn/ui Blocks, Shadcnblocks, Magic UI, Aceternity UI, 21st.dev, The Component Gallery |
| One section (nav, footer, CTA, hero) | Navbar Gallery, Footer, CTA Gallery, Details, Unsection |
| Product screens, onboarding, dashboards, flows | Mobbin, Refero, Nicelydone, SaaSFrame |

If browser tools are unavailable, still name the sources you would have opened and ask the user for screenshots or URLs they like.

## Memory artifact

Write **`web-references.md`** in the Forge memory directory during investigation or solution Phase 1 when this catalog applies:

```
## Job
[landing | product chrome | motion | section | app flow]

## Sources opened
- [name](url) — why this source

## Specific references
- [page or example](url) — what to steal (layout / type / motion / section) and what to reject

## Uncodixfy
- Applied / skipped (reason)
- Patterns banned for generated UI
```

## Catalog

### Awards

- [Awwwards](https://www.awwwards.com/) — Award-winning sites and agencies. Broader trends, experimental experiences, premium visual direction.
- [CSS Design Awards](https://www.cssdesignawards.com/) — Daily Website of the Day scored on UI, UX, and innovation. CSS-forward, jury-rated interactive sites.
- [CSS Winner](https://www.csswinner.com/) — Site of the Day/Month scoring. Second awards feed besides Awwwards and CSSDA.
- [The FWA](https://thefwa.com/) — Awards since 2000 for experimental, interactive, motion-heavy work. WebGL, immersive, boundary-pushing case studies.

### Full-site galleries

- [Godly](https://godly.design/) — Curated polished sites. Landing-page inspiration: typography, layouts, colors, interactions.
- [A1](https://www.a1.gallery/) — Hand-picked live-site gallery with boards and filters. Production landing-page references.
- [Httpster](https://httpster.net/) — Long-running showcase of clean, modern sites. Understated independent and studio aesthetics.
- [Land-book](https://land-book.com/) — Human-curated gallery plus section, color, industry, and platform filters. Deconstruct landings section by section.
- [Landing.Gallery](https://www.landing.gallery/) — Hand-picked landings tagged by stack. Pricing, careers, and marketing pages by how they were built.
- [Lapa Ninja](https://www.lapa.ninja/) — Thousands of landing examples with full-page screenshots and video. High-volume landing-page pattern scanning.
- [Minimal Gallery](https://minimal.gallery/) — Clean, functional sites since 2013. Restrained, editorial, whitespace-heavy references.
- [One Page Love](https://onepagelove.com/) — Single-page sites and section examples since 2008. One-page portfolios, launches, long-scroll landings.
- [Refs.Gallery](https://refs.gallery/) — Weekly award-level web experiences, including dark-UI collections. Cinematic, dark, immersive references.
- [SaaS Landing Page](https://saaslandingpage.com/) — Landings from well-known SaaS companies, browsable by page type. Conventional high-converting SaaS marketing layouts.
- [Saaspo](https://saaspo.com/) — Filtered SaaS gallery (landing, pricing, product, about, blog, integrations). Page-type research across live SaaS marketing sites.
- [SeeSaw](https://www.seesaw.website/) — Daily hand-picked feed of distinctive product, startup, and studio sites. Compact high-taste daily pass.
- [Siteinspire](https://www.siteinspire.com/) — Deep archive filtered by style, type, subject, and platform. Editorial, luxury, art-directed research.

### Motion

- [Motion Sites](https://motionsites.ai/) — Sites with strong animation and motion design. Transitions, scrolling effects, interactive storytelling.
- [landing.love](https://www.landing.love/) — Animation-site showcase with full-page video recordings. Watch scroll, 3D, and motion landings in motion rather than stills.
- [Hoverstat.es](https://www.hoverstat.es/) — Unusual web interactions: hover states, experimental nav, transitions. Non-generic, studio-level interaction ideas.

### React / components you can use

- [21st.dev](https://21st.dev/) — Reusable community-built UI components. Concrete React elements you can adapt.
- [Aceternity UI](https://ui.aceternity.com/) — React, Tailwind, and Motion components, blocks, and templates. Cinematic SaaS heroes, bento grids, motion effects — Uncodixfy before using in product chrome.
- [Magic UI](https://magicui.design/) — Open-source animated React + Tailwind components (shadcn companion). Marquees, bento, particles you can install.
- [shadcn/ui Blocks](https://ui.shadcn.com/blocks) — Official dashboard, sidebar, login, and app shells. Canonical shadcn page starters.
- [Shadcnblocks](https://www.shadcnblocks.com/) — Large set of shadcn/Tailwind/React blocks plus templates. Assemble marketing or dashboard UI from sections.
- [The Component Gallery](https://component.gallery/) — Component types across design systems with real examples. Compare tabs, pagination, trees, and more.

### Single sections (nav, footer, CTA, details)

- [Navbar Gallery](https://www.navbar.gallery/) — Navigation-only inspiration with live site links. Header, mega-menu, sticky-nav patterns.
- [Footer](https://www.footer.design/) — Footer-only gallery sortable by type and style. Closing-section and sitemap-footer layouts.
- [CTA Gallery](https://www.cta.gallery/) — Real call-to-action treatments tagged by industry and type. Conversion-button and signup-pattern research.
- [Details](https://www.details.so/) — Weekly captures of heroes, footers, preloaders, and micro-interactions. One section or motion detail at a time.
- [Unsection](https://www.unsection.com/) — Thousands of real website sections (hero, nav, footer, CTA, pricing), updated weekly. Mix-and-match section inspiration.

### Product screens / app UI

- [Mobbin](https://mobbin.com/) — Real iOS/web screens and flows, with Figma copy. Product UI, onboarding, checkout, app flows.
- [Refero](https://refero.design/) — Searchable web/iOS screens tagged by page type, UX pattern, and UI element. Pricing tables, navbars, dark mode from real products.
- [Nicelydone](https://nicelydone.club/) — Real SaaS screens, flows, and in-context UI components. Shipped dashboards, pricing, and product chrome — not mockups.
- [SaaSFrame](https://www.saasframe.io/) — SaaS website, product, and email screens, desktop and mobile. Compare landing, pricing, dashboard, and onboarding side by side.
