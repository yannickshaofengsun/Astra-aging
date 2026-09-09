# Setup and optional integrations

[Back to CareAnchor](../README.md)

All commands run from the repository root. The [quickstart](../README.md#run-locally) starts the application with Messages disabled.

## Live model connection

Live chat and coordination call `/Applications/ChatGPT.app/Contents/Resources/codex` using `gpt-6-astra`. The runtime path and model are defined in [astra_bridge.py](../careanchor/astra_bridge.py). A compatible signed-in desktop runtime, account with model access and network connectivity are required; calls use that account's model allowance. The repository does not install the runtime or include credentials.

The simulation works without inference. A failed model call produces an error instead of a scripted response. A fresh installation on a second machine has not been verified.

## Saved household

Starting `python3 server.py` saves the household under ignored `.runtime/mission-state.json`. **Saved rehearsal** offers explicit save and reload. Restoring a valid snapshot keeps pending responsibilities without repeating actions; invalid snapshots produce a visible load error and a fresh household. A failed write preserves the previous saved file and reports the failure.

Visit-change monitoring must be enabled again after a process restart. It watches a supplied fictional hospital source, not a real provider feed or physical sensors.

## Optional Apple Messages

Messages requires macOS access to the local Messages database, an approved one-to-one participant/account mapping, and saved household state. Keep private mappings in ignored `.runtime/messages-config.json`; never commit account details or derive recipients from message text. [imessage_bridge.py](../careanchor/imessage_bridge.py) validates `enabled` and `recipients`, with `actor_id`, `handle`, `account_id` and `inbound_account` for each participant. The two account identifiers are distinct and must be verified.

1. Start with `python3 server.py --messages-config .runtime/messages-config.json` and inspect `/api/messages/readiness`.
2. Explicitly POST to `/api/messages/baseline`, supplying the resident role and current household revision. This excludes older history. Configuration or receive-mode changes require a fresh baseline.
3. After that baseline exists, restart with the supervised receiver:

```sh
python3 server.py --messages-config .runtime/messages-config.json --messages-poll
```

The adapter processes new supported text messages from configured direct conversations. Groups, audio and attachments are excluded. Reception runs only while the server runs; there is no operating-system autostart.

For a controlled same-account rehearsal, start with all three flags: `--messages-config`, `--messages-poll` and `--messages-self-test`. It requires exactly one resident mapping; polling stays blocked until an explicit fresh baseline is established in that mode. Only new own-sent messages beginning with case-sensitive `Astra:` are accepted. This transport prefix is separate from the product name.

A successful send invocation is recorded as `submitted`; delivery and read remain unknown to the adapter. An uncertain send stays claimed across restart and is not automatically resent. When making a stopped-server backup, preserve the household snapshot, `.runtime/imessage-bridge.sqlite3` and private configuration together. Deleting the ledger is not a retry procedure.

## Editing the home scenes

Blender is optional: the browser uses included renders. Editable scenes and exports live in [assets/](../assets/); generation scripts live in [blender/](../blender/). Use an installed Blender executable to rebuild, for example:

```sh
blender --background --python blender/build_home.py -- --glb
```

[sketch-layout.json](../assets/sketch-layout.json) separates supplied facts, inferred geometry and unknown measurements. Rendered placement does not establish real dimensions, clearance, safe reach or installation feasibility.
