# CareAnchor

CareAnchor helps older adults arrange everyday support at home, connecting family and outside services around one shared plan. We are building toward the right help with less effort: use household preferences, budget and availability, reuse existing arrangements, and make each responsibility clear.

This hackathon prototype demonstrates hospital coordination. A resident asks for help, family members accept separate duties, and a changed appointment reopens the affected arrangements. Independent care-management practices are our initial customer hypothesis; reduced coordination effort remains an impact to test in real pilots.

## Demo

[**Watch the 60-second demo**](demo/careanchor-demo.mp4) · [Narration script](demo/transcript.md) · [Recording notes](demo/README.md)

[![CareAnchor demo](demo/preview.jpg)](demo/careanchor-demo.mp4)

The video has on-screen labels and AI-generated narration. It shows recorded app interactions with live GPT-6-Astra interpretations and fictional household data. It predates the optional visit-change monitoring below.

## Run locally

```sh
git clone https://github.com/yannickshaofengsun/CareAnchor.git
cd CareAnchor
python3 server.py
```

Open [CareAnchor](http://127.0.0.1:8765). The application uses Python's standard library and plain HTML, CSS and JavaScript; no package installation or frontend build is needed.

The simulation and included home renders work without a model connection or Blender. Live chat and coordination require a compatible signed-in macOS desktop Codex runtime with access to GPT-6-Astra. See [setup and optional integrations](docs/running.md) for runtime requirements, saved state, Messages and scene editing.

## Try visit coordination

1. In the resident chat, ask for a hospital visit: Alex drives there and home, and Morgan accompanies the resident.
2. In **Settings**, allow household updates and optionally record each helper's own dated availability. In **Resident → Visits**, allow hospital retrieval and visit requests; allow backup requests if reassignment should be possible.
3. Turn on **Watch visit changes**, then choose **Simulate hospital changing the visit**. CareAnchor checks the new notice, current plan and availability, then creates separate responsibility requests.
4. Switch to each helper's perspective to accept their own responsibilities. CareAnchor waits for those replies; an accepted duty does not establish physical attendance.

Monitoring covers changed notices for an existing fictional visit while the server runs. Your choice is saved with the household and restored after restart; new households and older saves default off. Pending responsibilities continue when helpers reply, without repeating the original request. Unchanged notices make no model calls.

## How it works

**Messages → model proposal → validated household plan → named replies.** CareAnchor is the product; GPT-6-Astra is the model. One shared household record holds preferences, permissions and responsibilities. The model proposes actions; application rules decide whether they can run. See [architecture and evidence boundaries](docs/architecture.md).

| Location | Contents |
| --- | --- |
| [careanchor/](careanchor/) | Household rules, model and messaging adapters, local server |
| [tests/](tests/) | Application and isolated adapter checks |
| [web/](web/) | Resident and family interface |
| [assets/](assets/) and [blender/](blender/) | Home scenes, renders and scene-generation scripts |
| [catalog/](catalog/) | Sourced product references and matching principles |
| [demo/](demo/) | Video, captions, recording notes and narration script |
| [docs/](docs/) | Setup and architecture |

## Checks

Run from the repository root:

```sh
python3 -m tests
python3 -m careanchor.mission_evaluation
```

The checks cover household rules, persistence, permissions, source changes and isolated adapters. The evaluator exercises authored scenarios; it does not measure real-world care outcomes or time savings.

## Prototype limits

This is a local simulation with fictional people and provider notices. The role selector is not authentication. Use fictional data: selected context is sent to the model. Physical services, purchases and robot movement are simulated; the optional Messages adapter can communicate with real people only when separately configured. Home illustrations and catalog matches do not establish safe fit, availability or completed installation.
