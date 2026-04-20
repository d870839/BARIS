# BARIS

A 2-player online-multiplayer remake of *Buzz Aldrin's Race Into Space* (1993), written in Python.

## Status

MVP skeleton. Two players can connect over websockets, pick sides, and advance seasons. One rocket, one mission, no animations — foundation to layer real BARIS mechanics on top of.

## Stack

- Python 3.13
- Pygame (client rendering)
- `websockets` (transport)
- SQLite (save/resume — not yet wired)

## Running locally

Open two terminals in the project root.

**Install deps** (one-time):
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Terminal 1 — server:**
```
python -m baris.server.main
```

**Terminal 2 & 3 — two clients:**
```
python -m baris.client.main --server ws://localhost:8765 --name Alice
python -m baris.client.main --server ws://localhost:8765 --name Bob
```

First player to connect is USA by default; second gets USSR. Either can change sides in the lobby before both ready up.

## Tests

```
pytest
```

## Roadmap

See [project memory](../../.claude/projects) and the TODO comments in code.
