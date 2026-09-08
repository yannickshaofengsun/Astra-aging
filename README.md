# Astra Aging

A hackathon household simulation: editable Blender homes, a shared household week, separate resident/family chats, and live GPT-6-Astra conversations. Three fictional U.S. household situations connect appointments, transport, paperwork, supplies, community activities, and home support. San Francisco public store/service options are a separate discovery layer.

## Codebase

The demo uses Python's standard library and plain HTML, CSS, and JavaScript. There are no pip packages, npm dependencies, database, or frontend build step. Python 3.14.6 was used to run all five test scripts successfully.

| File or folder | Purpose |
| --- | --- |
| `web/index.html` | Browser interface, resident/family views, chat, and household controls |
| `server.py` | Local HTTP server, JSON endpoints, and asset serving |
| `simulation.py` | Shared household state, role-filtered views, and scenario actions |
| `week.py` | Household-week planning, permissions, dependencies, and completion evidence |
| `astra_bridge.py` | Read-only conversation connection to the signed-in desktop Codex runtime |
| `comparison.py` | Matched manual-versus-assisted simulation replays |
| `real_world.py` | Curated San Francisco public store and service references |
| `blender/` and `assets/` | Scene-generation scripts, editable scenes, exports, and rendered images |
| `test_*.py` | Five runnable check scripts for simulation, week, comparison, catalog, and server behavior |

## Open the demo

For a fresh checkout:

```sh
git clone https://github.com/yannickshaofengsun/Astra-aging.git
cd Astra-aging
```

From this folder, run:

```sh
python3 server.py
```

Open [the household demo](http://127.0.0.1:8765). The server binds only to this computer. Live chat uses the existing signed-in desktop runtime at `/Applications/ChatGPT.app/Contents/Resources/codex` and `gpt-6-astra`; it uses your existing model allowance. The older standalone CLI could not refresh this model's metadata, so the compatible desktop runtime is used without changing global configuration. If Astra fails, the app shows an error instead of substituting a scripted response.

The simulation and included home renders work without Blender or a model connection. Live chat requires the compatible macOS desktop runtime at the path above, a signed-in account with model access, and network access. Its runtime path and model are constants in `astra_bridge.py`; this repository does not provide credentials or install that runtime.

Try the shared week:

1. Choose a fictional household. Expand **Household preferences and permissions** to edit independent preferences and bounded permissions.
2. Grant the routine permissions you want to test. Expand **Try a change in this fictional week** and introduce the clinic conflict.
3. Choose which commitment to preserve, then let the assistant complete permitted administration. Clinic acknowledgment and a requested ride remain separate facts.
4. Switch to Family to accept or decline the requested help. Try moved paperwork, unavailable supplies, cancellation, and a home-comfort need. A reported location, order acknowledgment, delivery, placement, and resident feedback are separate stages.
5. With **Your house sketch** selected, choose the illustrative bedside-caddy option. Preview the proposed change; preparation of a request does not establish installation.
6. Expand **Compare manual and assisted administration** for actual matched replays across all three situations.
7. Explore **Public options in San Francisco** by need and optional budget. Review official sources, unknowns, and preparation checklists. These are public references; no provider has been contacted.

The separate garden practice story:

1. Select **Your house sketch** or the **Example household**.
2. Try the clearly fictional garden activity, or choose **Keep my usual routine**.
3. If you try it, click the highlighted invitation, bedroom tote, and departure markers. The avatar moves as you prepare; the sketch's departure point is illustrative.
4. Optionally request company. Switch to Family to accept that request; readiness waits for acceptance if help was requested.
5. Replay to try a different choice. These are simulated outcomes, with no real signup or support request.

The separate appointment scenario remains available:

1. Move the appointment to Thursday. The previous ride confirmation becomes invalid.
2. Ask the resident chat what still needs arranging.
3. Switch to Family. Confirm or decline the new pickup.
4. Move the documents. Their recorded location becomes **last known**.
5. Switch to Resident and confirm the new document location.
6. Reset to replay the scenario. Each chat channel has its own conversation.
7. Select **Your house sketch**. Ask Astra which room facts are confirmed and which dimensions are unknown. Expand **What Astra knows** to inspect its house context. Changing homes clears both conversations; Reset preserves the selected home.

Live Astra explains the supplied plan and public source snapshots. The routine-assistant button executes explicit simulation rules within standing permissions; generated chat text cannot silently confirm transport, order equipment, or establish physical completion.

## Blender

`assets/home.blend` is the editable source scene; `assets/home.png` is its rendered overview; `assets/home.glb` is an exchange export. The browser uses the render, so this version tests coordination behavior rather than physical motion or renovation feasibility.

`assets/sketch-home.blend`, `.png`, and `.glb` reconstruct your latest interior sketch approximately. Three bedrooms and their queen beds are user-confirmed; the upper-left bedroom is R1. Other bedroom numbers remain unresolved. The two-apartment/eight-units-per-floor context is recorded, while the remaining apartments are not modeled. `assets/sketch-layout.json` separates confirmed facts, inferred geometry, and unknowns. Real dimensions, exact openings, and clearances are unmeasured. The source photos are not served by the web app.

`assets/sketch-adapted.blend` and `.png` show a proposed generic bedside caddy in R1 using the same camera. The original scenes remain unchanged. This generic $25 simulation fixture is separate from products in the public catalog; neither the visual nor a listed product establishes fit, safe reach, availability, or installation.

Blender is only needed to edit or rebuild scenes; the repository includes the generated assets. The following commands use the original workstation's local download, which is excluded from Git. On another machine, use your installed Blender executable in place of the `.runtime/` executable below.

The official Blender 4.5.13 ARM build is retained locally in `.runtime/`, with its published SHA-256 verified. It is mounted read-only, not installed into Applications. If the local download exists but the mount is absent after restart:

```sh
hdiutil attach -readonly -nobrowse -mountpoint "$PWD/.runtime/blender" "$PWD/.runtime/blender-4.5.13-macos-arm64.dmg"
```

Open the source scene:

```sh
open -a "$PWD/.runtime/blender/Blender.app" "$PWD/assets/home.blend"
```

Rebuild the scene and render:

```sh
.runtime/blender/Blender.app/Contents/MacOS/Blender --background --python blender/build_home.py -- --glb
```

Rebuild the sketch variant with `--python blender/build_sketch_home.py` using the same Blender binary.

## Project coordination

[Paperclip: Astra Aging](http://127.0.0.1:3100/LAU/projects/astra-aging) holds the baseline work LAU-14 through LAU-20, household-week expansion LAU-21 through LAU-24, and San Francisco discovery LAU-25. The local, untracked `.coordination/paperclip.json` records issue IDs, statuses, and worker mappings. Paperclip is not required to run the demo. The central coordination task is `01a0821f-4f9a-7b12-a7b8-a9747fd76124`.

Separate Codex tasks:

- **Build resident and family chats** — `01a0821a-8f95-7993-8bde-d260ce7501b1`, owns `web/index.html`.
- **Connect Astra household conversations** — `01a0821a-9180-76b3-8ff9-2d53becfc024`, owns the local server and Astra connection.

Codex subagents built the Blender scene and configured Paperclip. The coordinator records verified progress in Paperclip; automatic Paperclip-to-Codex synchronization and recurring agent runs are not configured. The existing unrelated Paperclip agent was preserved.

## Checks and boundaries

```sh
python3 test_simulation.py
python3 test_week.py
python3 test_comparison.py
python3 test_real_world.py
python3 test_server.py
```

Role tabs demonstrate filtered perspectives, with no login or real access control. The resident's fictional private appointment reason is omitted from the family view and family model context. Chat sends the selected role's scenario and selected house facts to OpenAI; the app is not offline. Do not enter real health information or personal appointments.

The matched replay records 19 manual versus 18 assisted human interactions in the nearby-support and couple cases, including setup; excluding setup gives 18 versus 16. The remote-helper case records 14 versus 14 including setup, with required work unresolved. Family-role interactions are unchanged in every pair: this does not demonstrate reduced unpaid family work or time. These are scripted role-bucket counts, with bundled setup and already-identified tasks, not individually measured workload, longitudinal results, or population estimates.

State is held in memory and restarts fresh. No real appointments, events, messages, rides, clinical decisions, or bookings occur. The week uses fixed fictional offers and response rules; no clock advances. Invitation/tote markers are fictional game props projected through the Blender cameras, not observed belongings. Scene dimensions are illustrative; avatar transitions do not validate navigation, mobility, accessibility, or safety. Robot training and physical interaction are future extensions.

The San Francisco catalog is a curated official-source snapshot checked on September 8, 2026, with no live availability feed or provider integration. A listed item price does not establish an affordable delivered total. Public matches and checklists remain **not requested**; simulated orders and reports never change real-world coordination status.

See `PROJECT.md` for the shared implementation contract.
