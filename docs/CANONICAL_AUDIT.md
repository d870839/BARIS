# Canonical BARIS audit — current state

Refresh of the "what's still missing vs. the 1993 game" table. Run
after Q-deep, R-deep, and P-deep landed; before the next divergence
push.

## Hardware tree

| Canonical feature | Status | Notes |
|---|---|---|
| Rocket classes (light/medium/heavy) | ✅ | `Rocket.LIGHT/MEDIUM/HEAVY`, side-aware display names |
| Per-unit reliability tracking | ✅ | R-deep |
| Stand tests on individual units | ✅ | Max-Q + Full-up, R-deep |
| Service Module separate from Capsule | ✅ | Q-deep |
| Tiered injection stages (Kicker A/B/C) | ✅ | Q-deep |
| Probe families (lunar / inner / outer) | ✅ | Q-deep |
| LM as distinct component | ✅ | Phase Q |
| EVA suit | ✅ | |
| Docking module | ✅ | |
| Capsule families (1-man / 2-man / 3-man) | ✅ | Capsule-deep — `CAPSULE_1` (Mercury) / `CAPSULE_2` (Gemini) / `CAPSULE_3` (Apollo), routed by `mission.crew_size`, hard-prereq through the existing Q-deep gate. |
| Joint missions / multi-rocket payloads | ✅ | EOR-architecture lunar landing now consumes two Medium-rocket units (CSM-leg + LM-leg) and rolls a `RENDEZVOUS` phase. Each leg has its own unit reliability snapshot. |
| Hard reliability prereqs | ✅ | Q-deep |
| Side-specific hardware names | ✅ | `rocket_display_name(rocket, side)` |

## Astronauts

| Canonical feature | Status | Notes |
|---|---|---|
| Recruitment in groups | ✅ | Phase J, 4 groups |
| Five skill tracks (Capsule, LM, EVA, Docking, Endurance) | ✅ | |
| Basic + advanced training | ✅ | |
| Compatibility / personality | ✅ | A/B/C/D types |
| Mood / morale | ✅ | |
| Fatigue / rest between flights | ✅ | Phase T |
| Hospital recovery | ✅ | |
| KIA tracking | ✅ | |
| Memorial Wall | ✅ | Phase N |
| Crew assignment (manual + auto) | ✅ | Phase O + crew roles |
| Per-seat skill roles | ✅ | Crew roles within missions |
| Per-character bios + glyph + swatch | ✅ | Brainrot divergence |
| Character 3D models | ✅ | Procedural fruit-bodies (this session) |
| **Retirement triggered by code path** | ⚠️ | `AstronautStatus.RETIRED` exists but isn't currently set anywhere. Original: long-tenure / low-mood astronauts retire. |
| **Veteran tier / experience-gated missions** | ❌ | All astronauts uniform; no "you need a veteran for this flight" |
| **Astronaut classes (military pilot vs scientist)** | ❌ | Roster is uniform |
| **Defection / scandal events** | ⚠️ | News pool has a defector entry; effect is prestige-only, no astronaut actually leaves |
| **Press conferences / public events** | ❌ | |

## Mission catalog & resolution

| Canonical feature | Status | Notes |
|---|---|---|
| Tiered mission unlocks | ✅ | Tier 1 / 2 / 3 |
| Sub-objectives (EVA, docking, etc.) | ✅ | Phase E |
| Architecture choice (DA / LOR / EOR) | ✅ | |
| First-claim bonus | ✅ | |
| Step-by-step per-phase resolution | ✅ | Real Phase P |
| Partial successes | ✅ | P-deep |
| Per-phase consequence tables | ✅ | P-deep |
| Cinematic phase reveal | ✅ | |
| Catastrophic crew loss path | ✅ | |
| Pad damage on catastrophe | ✅ | |
| Budget cut on manned failures | ✅ | |
| Mission history / museum | ✅ | Phase L |
| **Joint / rendezvous missions** | ❌ | Same gap as joint hardware above |
| **Capsule recovery operation roll** | ❌ | Original rolled a separate "recovery successful?" check after splashdown |
| **Lunar surface multi-stage objectives** | ⚠️ | We have moonwalk + sample return; original split into surface time, samples, deployment of equipment, etc. |

## Game flow & meta

| Canonical feature | Status | Notes |
|---|---|---|
| Turn-based seasons | ✅ | |
| Calendar deadline year | ✅ | Phase S, default 1977 |
| Historical milestones | ✅ | Phase S — Sputnik, Yuri, Kennedy, Apollo 1, decade-end |
| Government review / firing | ✅ | Phase M |
| News events | ✅ | Phase I |
| Save / load | ✅ | Phase U |
| Prestige tiebreaker on game end | ✅ | |
| Auto-save on every state change | ✅ | Phase U |
| **Multiple game lengths** | ❌ | Currently fixed end-year |
| **Difficulty levels** | ❌ | Single difficulty |
| **Alt-history scenarios (1945 start, retired Saturn V, etc.)** | ❌ | Divergence wishlist |
| **Persistent cross-game records (museum across sessions)** | ❌ | Polish wishlist |

## Multiplayer / opponents

| Canonical feature | Status | Notes |
|---|---|---|
| Same-room PvP multiplayer | ✅ | Websocket server, full state autosync |
| Cross-base visibility | ✅ | Divergence — opponent silhouette visible |
| Intel / espionage | ✅ | Phase H — opponent reliability estimates, rumored mission |
| Sabotage cards | ✅ | Divergence — 4 cards |
| Radio chatter | ✅ | Divergence |
| **AI opponent for solo play** | ❌ | Phase V on the roadmap |
| **Co-op vs AI** | ❌ | Divergence wishlist |
| **Spectator mode** | ❌ | Divergence wishlist |

## Visuals / interaction

| Canonical feature | Status | Notes |
|---|---|---|
| 3D facility with walk-in interiors | ✅ | R&D, MC, Astro, Library, Intel, Museum |
| Walking-around player camera | ✅ | |
| Procedural buildings + silhouettes + atmosphere | ✅ | |
| Cinematic launch + ascend animation | ✅ | |
| Per-phase reveal in result panel | ✅ | |
| Character 3D models | ✅ | Fruit characters (this session) |
| Pad status markers + flame puffs | ✅ | |
| Cross-base opponent silhouette | ✅ | |
| Pygame overlay for crisp UI | 🚧 | Step 1-3a shipped; result panel migrated |
| **Sound / music** | ❌ | Out of scope so far |
| **First-run tutorial / onboarding** | ❌ | Polish wishlist |

## Recommended next priorities

Ranked by canonical impact + how blocking they are for a real game:

1. **AI opponent (Phase V)** — biggest single missing canonical
   feature. Solo play unlocks a much wider audience.
2. **Finish UI overlay refactor** — port R&D + MC panels next so
   the wonky 3D-rendered menus retire.
3. **Difficulty + game-length settings** — quick to ship, big
   replay-value win.
4. **Wire retirement + defection consequences** — both have data
   model hooks but don't actually remove astronauts; a one-day
   polish round.
5. **Persistent cross-game records** — museum that survives
   server restarts; polish wishlist.
6. **Asymmetric tech trees** — divergence wishlist; biggest
   identity-shift after the Italian Brainrot roster.

## Items intentionally **not** on the audit

These are original BARIS features we're explicitly skipping in
favour of divergence:

- Real-name astronauts (we replaced with Italian Brainrot characters)
- Cold War politicking minutiae
- Pixel-art photo cinematics (we have procedural 3D)
- Specific BARIS UI metaphor (we shipped a different layout)
