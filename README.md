# BARIS

A 2-player online-multiplayer remake of *Buzz Aldrin's Race Into Space* (1993), written in Python.

Clean-room reimplementation — mechanics and historical content (Mercury Seven, Vostok/Voskhod/Soyuz, Saturn V/N1, etc.) come from public historical record, not from the original game's code.

## Quick start

One-time setup:
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Run it (one terminal — the easy way):**
```
.venv\Scripts\activate
python -m baris.dev
```
That spawns the server plus two client windows. Ctrl+C in the terminal stops everything.

**Dev/debug mode** — preseeds both players with a fat budget, all rockets built, and Apollo/Soyuz already unlocked so you can test manned lunar landings immediately without grinding R&D:
```
python -m baris.dev --debug
```

**Manual launch** (three terminals) if you want separate logs or you're connecting remote clients:
```
# Terminal 1
python -m baris.server.main            # add --debug for debug mode

# Terminal 2
python -m baris.client.main --name Alice

# Terminal 3
python -m baris.client.main --name Bob --server ws://HOST:8765
```

## Experimental 3D client

A first-person Ursina client is under `baris.client3d`. It talks to the same
websocket server as the 2D client, so they can coexist — you can run one of
each against the same game.

Install (separate deps):
```
pip install -r requirements-3d.txt
```

Run against a running server:
```
# Terminal 1
python -m baris.server.main --debug

# Terminals 2 and 3
python -m baris.client3d.main --name Alice
python -m baris.client3d.main --name Bob --server ws://HOST:8765
```

Walk with **WASD** + mouse look. Approach Mission Control and press **E** to
open the turn-submit panel; **Esc** closes. V1 only supports pass turns — R&D,
missions, briefings, and the launch sequence still live in the 2D client.

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
# One-time setup
git clone <your-fork-url> baris
cd baris
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
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
- First run on Windows may trigger a firewall prompt for the Python client;
  allow it on private networks.
- 3D client is heavier (pulls in `ursina` + `panda3d`, ~50 MB). If install
  fights you, fall back to the 2D client — they talk to the same server, so
  mixing 2D and 3D in one game works fine.

## Controls

**Lobby:**
- `1` pick USA, `2` pick USSR, `Enter` ready/unready.

**In-game:**
- `Q` / `W` / `E` — set R&D target to Light / Medium / Heavy rocket.
- `←` / `→` — adjust R&D spend by 5 MB.
- `1`–`9`, `0`, `-` — queue mission (see on-screen list).
- `Esc` — cancel queued mission.
- `Enter` — submit turn. Season advances once both players submit.
- Once Apollo/Soyuz unlocks: `A` = Direct Ascent, `S` = Earth Orbit Rendezvous, `D` = Lunar Surface Rendezvous, `F` = Lunar Orbit Rendezvous. One-way choice.

## Winning

- **First successful manned lunar landing** ends the game immediately.
- Secondary: first to **40 prestige** wins if nobody's landed yet.

## Game structure

Three eras (program tiers). Each side's real-world program names:

| Tier | USA | USSR | Missions |
|------|-----|------|----------|
| 1 | Mercury | Vostok | sub-orbital, satellite, unmanned orbital, manned orbital |
| 2 | Gemini | Voskhod | multi-crew orbital, orbital EVA, lunar flyby, unmanned lunar orbit |
| 3 | Apollo | Soyuz | unmanned lunar landing, manned lunar orbit, manned lunar landing |

Tier 2 unlocks after any Tier 1 success by that player; Tier 3 after any Tier 2 success.

## Tests

```
pytest
```

## Status

Working MVP with historical flavor: Mercury Seven + real Soviet cosmonauts (including Tereshkova, first woman in space), per-side rocket names (Redstone/Titan II/Saturn V vs R-7/Proton/N1), program tiers, rocket reliability ratings, crew selection and mortality, and all four historical lunar mission architectures.

Not yet: historical event cards, calendar-driven milestones, explicit training focus, manual crew picks, deployed server for internet play.
