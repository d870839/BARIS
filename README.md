# BARIS

A 2-player online-multiplayer remake of *Buzz Aldrin's Race Into Space* (1993), written in Python.

Clean-room reimplementation — mechanics and historical content (Mercury Seven, Vostok/Voskhod/Soyuz, Saturn V/N1, etc.) come from public historical record, not from the original game's code.

You can play either in a **2D pygame tab UI** or walk around the facility in a **3D first-person walkaround**. Both talk to the same server; you can mix them in one match.

## Quick start

One-time setup:
```
python -m venv .venv
source .venv/bin/activate            # macOS / Linux
.\.venv\Scripts\activate              # Windows PowerShell
.venv\Scripts\activate.bat            # Windows cmd.exe

pip install -r requirements.txt       # 2D client (smaller, safer)
# or, for the 3D walkaround:
# pip install -r requirements-3d.txt
```

**Run it (one terminal — the easy way):**
```
python -m baris.dev
```
Spawns the server plus two 2D client windows. Ctrl+C stops everything.

**Debug mode** — preseeds both players with a fat budget, all rockets built, and Apollo/Soyuz already unlocked so you can go straight to lunar missions:
```
python -m baris.dev --debug
```

**3D mode:**
```
python -m baris.dev --mode 3d --debug --auto-ready
```
`--auto-ready` makes the 3D clients skip the lobby; the 2D client still needs a manual Enter.

**Solo testing.** The server always needs two players — there's no true single-player mode — but `baris.dev` spawns both windows for you, so ready both and just ignore one. If you want pure isolation:
```
python -m baris.dev --clients 0        # server only; connect your own clients
```

**Manual launch** (three terminals, for separate logs or connecting remote clients):
```
# Terminal 1
python -m baris.server.main            # add --debug for debug mode

# Terminal 2
python -m baris.client.main --name Alice

# Terminal 3
python -m baris.client.main --name Bob --server ws://HOST:8765
```

## Which client?

| | **2D tab UI** | **3D walkaround** |
|-|-|-|
| Install | `requirements.txt` (pygame) | `requirements-3d.txt` (ursina + panda3d, ~50 MB) |
| Input | mouse + keyboard, tab-based | WASD + mouse look, walk into buildings |
| Speed to play a turn | fast — every screen is a hotkey away | slower — you literally walk between rooms |
| Gameplay coverage | full | full (mixes fine with 2D in the same match) |

Both clients support: lobby + side pick, R&D, mission queueing, objective toggles, architecture choice, full odds breakdown, launch animation + result panel, astronaut roster with mood + compatibility, advanced training, recruitment (Phase J), intelligence reports (Phase H), seasonal news (Phase I), mission history + prestige timeline (Phase L), event log, and scheduled-launch scrub.

The 3D client adds flavour the 2D can't: a physical hub you walk between, live-updating Mission Control briefing TV, a bar-chart prestige timeline in the Museum, portrait-wall roster in the Astronaut Complex, and a dim Intelligence Office with a wall dashboard.

## Playing with friends over the internet

BARIS is 2-player. There's no hosted matchmaking server yet — you host, your
friend connects. The server already binds `0.0.0.0:8765`, so the only missing
piece is a public URL. Cloudflare Quick Tunnels are the low-friction option:
no account, no signup, URL good for as long as the terminal stays open.

### Host (you)

One-time: install `cloudflared`.
- macOS: `brew install cloudflared`
- Windows: `winget install Cloudflare.cloudflared`
- Linux: grab the binary from Cloudflare's downloads page.

Each session, two terminals:
```
# Terminal 1 — public tunnel to your local server
cloudflared tunnel --url http://localhost:8765
#   prints: https://<random-words>.trycloudflare.com   <-- send this to your friend

# Terminal 2 — the game server
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m baris.server.main      # add --debug to pre-seed budget + rockets
```

Then launch your own client against the *local* server (faster, no round trip
through the tunnel):
```
python -m baris.client.main --name YourName
```

Close both terminals when you're done; the tunnel URL is single-use and
changes on the next run.

### Friend (the other player)

Send them this block. They'll need Python 3.11+ and git.

```
# One-time setup — swap in your fork's URL (e.g. https://github.com/<you>/BARIS.git)
git clone <your-fork-url> baris
cd baris
# Active development happens on a feature branch, not main:
git checkout claude/pull-baris-data-wd2K4

python -m venv .venv
# Activate the venv — pick the one for your shell:
source .venv/bin/activate             # macOS / Linux
.\.venv\Scripts\activate               # Windows PowerShell
.venv\Scripts\activate.bat             # Windows cmd.exe

pip install -r requirements.txt          # 2D client
# or, for the 3D walkaround client:
# pip install -r requirements-3d.txt

# Each session — replace the URL with what the host sent
python -m baris.client.main --name FriendName \
    --server wss://<random-words>.trycloudflare.com
# 3D: python -m baris.client3d.main --name FriendName --server wss://...
```

Notes:
- **`wss://`** (TLS), not `ws://`, and **no `:8765`** — the tunnel handles both.
- **Windows PowerShell — "running scripts is disabled":** if activating the
  venv fails with an execution-policy error, run this once as your user
  (answer `Y` when prompted), then reopen the terminal:
  ```
  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
  ```
- First run on Windows may trigger a firewall prompt for the Python client;
  allow it on private networks.
- 3D client is heavier (pulls in `ursina` + `panda3d`, ~50 MB). If install
  fights you, fall back to the 2D client — they talk to the same server, so
  mixing 2D and 3D in one game works fine.

## Controls

### 2D client

**Lobby**
- `1` pick USA, `2` pick USSR, `Enter` ready/unready.

**In-game tabs** (switch with F-keys)
- **F1** Hub — clickable building map.
- **F2** R&D — rocket / module research.
- **F3** Astronauts — roster with mood + compatibility; `R` recruits the next group.
- **F4** Missions — queue a launch, toggle objectives.
- **F5** Intelligence — `I` requests a report (10 MB, one per season).
- **F6** Museum — mission history + prestige-over-time chart.
- **F7** Event log.

**Turn actions (mostly on the R&D + Missions tabs)**
- `Q` / `W` / `E` — set R&D target to Light / Medium / Heavy rocket.
- `R` — set R&D target to the Docking Module.
- `←` / `→` — adjust R&D spend by 5 MB.
- `1`–`9`, `0`, `-` — queue a mission from the on-screen list.
- `V` / `B` / `N` / `M` / `,` — toggle objectives (EVA / docking / long duration / moonwalk / sample return).
- `Esc` — cancel queued mission.
- `Enter` — submit turn. Season advances once both players submit.
- Tier 3 unlock (once Apollo/Soyuz is available): `A` = Direct Ascent, `S` = EOR, `D` = LSR, `F` = LOR. One-way choice.

### 3D client

- **WASD** — walk. **Mouse** — look.
- **E** — interact with whatever you're standing next to (open door, press console button, confirm a pick).
- **Esc** — close panel / walk out of an interior.
- Buildings on the hub: Mission Control, R&D Complex, Astronaut Complex, Library, Intelligence Office, Museum.

## Winning

- **First successful manned lunar landing** ends the game immediately.
- Secondary: first to **40 prestige** wins if nobody's landed yet.

## Game structure

Three eras (program tiers). Each side's real-world program names:

| Tier | USA | USSR | Missions |
|------|-----|------|----------|
| 1 | Mercury | Vostok | sub-orbital, satellite, unmanned orbital, manned orbital |
| 2 | Gemini | Voskhod | multi-crew orbital, orbital EVA, lunar flyby, unmanned lunar orbit, planetary flybys (Venus / Mars / Mercury / Jupiter / Saturn) |
| 3 | Apollo | Soyuz | orbital docking, LM Earth test, LM lunar test, unmanned lunar landing, manned lunar orbit, manned lunar landing |

Tier 2 unlocks after any Tier 1 success by that player; Tier 3 after any Tier 2 success.

Extra systems layered on top:
- **Five skills** per astronaut — Capsule / LM Pilot / EVA / Docking / Endurance — influence manned-mission success by the crew's average in the primary skill.
- **Compatibility letters** (A/B/C/D) across the crew give a small success bonus; opposites (A↔C, B↔D) give a small malus.
- **Mood** (0-100) drifts toward 60 each season, bumps on success, drops on failure + extra on KIA. Low enough and an astronaut retires.
- **Training** — basic training keeps new recruits off the flight line for a few seasons; advanced training buys +2 in a chosen skill over two seasons.
- **Hospital** — failed manned missions can put survivors in recovery.
- **Recruitment groups** — four historical intakes, each gated behind a year + cost. Group 1 = starting Mercury Seven / Vostok cohort; groups 2-4 add New Nine / Fourteen / Nineteen style reinforcements.
- **Three launch pads** — A/B/C, each tracks its own scheduled launch and can be damaged by catastrophic flights.
- **Rocket reliability** — built by stochastic R&D rolls, bumped on success, clipped on failure, and floored once a rocket is proven.
- **Lunar reconnaissance** — unmanned lunar probes build a recon percentage that adds to manned-landing success, offset by missing LM points.
- **Hardware modules** — Docking, Lunar Kicker, EVA Suit — each researched separately with missions that require them as prereqs.
- **Seasonal news** — a weighted card fires each season: budget windfalls, press tours, defectors, hardware recalls, morale boosts, scandals.
- **Intelligence** — spend 10 MB per season to get a noisy snapshot of the opponent's hardware reliability + rumored next mission (80% accurate).
- **Museum** — permanent record of every launch and a per-season prestige timeline you can visit.

## Tests

```
pytest
```

Currently ~160 tests across state, resolver, and the end-to-end handshake.

## Status / roadmap

Working multiplayer game with historical flavour: Mercury Seven + real Soviet cosmonauts (including Tereshkova, first woman in space), per-side rocket names (Redstone/Titan II/Saturn V vs R-7/Proton/N1), program tiers, the four historical lunar architectures (DA/EOR/LSR/LOR), and the full progression from sub-orbital to manned lunar landing.

**Shipped phases (A–L in the feature plan):**
A 5-skill crew model · B multi-turn VAB scheduling · C training + hospital · D lunar recon + LM points · E three launch pads · F hardware modules (docking, lunar kicker, EVA suit) · G expanded mission catalog (flybys, docking, LM tests) · H intelligence room · I seasonal news · J recruitment groups · K compatibility + mood + retirement · L museum + prestige timeline.

**Not yet:**
- **M — Government Review.** End-of-year eval with dismissal risk if you're underperforming.
- **N — Memorial wall.** Small Arlington / Kremlin Wall entity listing KIA crew.
- Persisted cross-game records (Museum currently remembers the current game only).
- Historical calendar deadlines (e.g. a literal 1969 milestone).
- A hosted server so friends don't need a tunnel.
