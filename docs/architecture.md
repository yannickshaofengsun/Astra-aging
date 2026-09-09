# Architecture and evidence

[Back to CareAnchor](../README.md)

## One household plan

The browser, Messages adapter and coordinator use the same household record. Preferences describe how a person wants help; availability describes when someone may help; responsibilities record what a named person actually agreed to do. A general preference or relationship never substitutes for a particular acceptance.

[simulation.py](../careanchor/simulation.py) owns shared state, revisions and role-filtered views. [coordination.py](../careanchor/coordination.py) owns requests, permissions, scoped memory and named replies. Domain modules keep the evidence required for their work, such as provider notices and travel duties in [hospital.py](../careanchor/hospital.py).

## Proposals and effects

[astra_bridge.py](../careanchor/astra_bridge.py) requests structured proposals from GPT-6-Astra through the signed-in desktop runtime. [server.py](../careanchor/server.py) checks the current context and passes proposals through household validators. A model-generated sentence cannot grant permission, accept another person's duty or establish physical completion.

[proactive.py](../careanchor/proactive.py) detects a changed fictional visit notice and reuses the same coordination path. It rechecks permission and dated availability after inference, keeps a stable request identity for the notice, and waits for each person's reply. Unchanged notices do not trigger model calls; disabling monitoring or revoking permission prevents new automatic work.

Changed source facts invalidate only affected arrangements. An old acceptance cannot silently become acceptance of a new date, destination or responsibility. Keep requested, accepted, delivered and physically completed states distinct.

## Memory and recovery

Resident-selected sharing applies before context reaches the model or a family view. People can inspect, correct and forget supported preferences. Forgetting removes retired memory-bearing request text and proposed values from current saved state; it does not erase existing backups or data already sent to a model.

[persistence.py](../careanchor/persistence.py) validates and atomically saves local snapshots. Reload restores facts and pending work without replaying effects; stale revisions cannot authorize new actions. Messages receipt cursors and send claims live separately in SQLite, because an uncertain external send must not be repeated merely after a restart. [Setup notes](running.md#optional-apple-messages) explain the backup boundary.

Role filtering demonstrates intended visibility within this prototype. It is not authenticated multi-person or multi-household access.

## What the evidence establishes

Automated checks exercise state transitions, permissions, cancellation, stale context and recovery using fictional data. Live GPT calls have also been exercised for request interpretation, memory changes and background visit changes. These establish those tested paths, not general autonomous care.

A controlled same-account Apple Messages rehearsal observed intake, a real model call and an automatic reply displayed as Delivered in the native app. A separate older-adult device, voice intake and a new proactive Messages round trip have not been verified. Adapter send status and native delivery evidence remain different observations.

[Video notes](../demo/README.md) describe the recording's scope. [Catalog notes](../catalog/README.md) distinguish sourced product facts from proposed matches. Provider responses, purchases, care delivery and robot movement are simulated. Authored comparisons do not establish reduced family workload, elapsed time, clinical benefit or willingness to pay.
