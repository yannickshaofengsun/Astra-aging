# Family memory, organization, and independent operation

[Back to README](../README.md) · Code paths in this document are relative to the repository root.

Requested on September 8, 2026. The user asked to coordinate agent memory and family organization, and clarified that self-deployment means both a family installing/running the system and the agent continuing coordination on its own.

The first continuity delivery is implemented. The broader autonomous-operation and family-installation layers below remain a deployment design. The central coordination task owns sequencing and the canonical Messages session; **Find previous AI for aging idea** remains the integration lead. This task implemented `coordination.py` and its checks after central transferred their ownership; existing service, household, hospital and interface owners integrated the shared contract.

The implemented memory covers delivery-window, message-detail and routine preferences, with resident-selected sharing, correction and forgetting. The existing fictional Alex/Morgan roster now supports self-reported, inclusive date intervals. This is not yet an arbitrary-family onboarding system or a general personal-facts store. Native Settings controls and natural resident remember/forget requests use the same state. No hosted service was deployed by this work.

Continuity verification checkpoint (September 8, 2026): all 15 repository check scripts passed after that delivery's final source changes, including 34 server cases. Two actual Astra calls through an isolated server completed a private remember request and subsequent forget request; both family model contexts excluded the private selection. The interface owner verified resident edit/share/forget, own-person date ranges, stale controls and permission-only saves at narrow and desktop widths. These tests use fictional households and establish no real-world care outcome.

Forgetting or superseding a recorded preference also erases its retired memory-bearing request text and proposed value from current saved state. A digest, record ID and action status retain duplicate detection without restoring the erased text. Equal direct memory edits leave source, history and memory revision unchanged. Existing backups and data already sent to a model are separate retention boundaries; this change does not claim to erase those copies.

## Decision

Use one shared household record, the existing task/action system, and one bounded coordinator. Family organization describes who can help and on what terms; memory preserves what has been established; the task system records what is currently owed and what actually happened. They must reference the same people and plans.

Do not create an agent for every family member or a second household plan. A relationship model can use ordinary records; it does not require a graph database. Semantic search is optional when a measured retrieval problem justifies it.

## Verified code foundations

Source inspection on September 8, 2026 found:

| Existing seam | Reuse and remaining gap |
| --- | --- |
| `coordination.py`: actors, preferences, permissions, requests, pending responsibilities, recent request context | Named Alex/Morgan duties and some continuity already exist. The actor catalog and proposal identifiers are fixed demo fixtures; expand the shared actor definition consistently before supporting arbitrary families. |
| `Coordination.reply_context` and `Household.recipient_context` | Named people reply to their own duties; ambiguous replies do not imply acceptance. Keep this boundary when memory is added. |
| `simulation.py`: shared views, revisions and validated mutations | Use the same state for Messages, family interface and agent actions. Do not let retrieved text bypass validators. |
| `persistence.py`: validated atomic household snapshots | Saves already include coordination, week, mission and other scenario domains. Extend the established format and restoration checks for new records; do not replace storage merely to add memory. |
| `imessage_bridge.py`: private participant mappings and a local SQLite bridge store | Reuse the adapter's durable identities and delivery records. Its configured actors are currently resident/Alex/Morgan. Actual channel access and successful delivery remain separate verification steps. |
| `astra_bridge.py`: bounded desktop model bridge | The current model and macOS application path are constants. A family-installed version needs explicit runtime configuration and a setup check on that family's machine. |

These observations establish implementation seams, not passing tests for the proposed additions or successful real Messages access. The current loopback demo's actor selector is not authenticated identity.

## 1. Family organization

Maintain a single household roster referenced by tasks, memory, permissions and channel mappings:

- Stable person ID, display name, relationship and explicitly linked communication identity.
- Roles and responsibilities the person is willing and permitted to take: driving, visit companionship, paperwork, purchasing or equipment setup. Relationship alone grants no authority.
- Availability with a date/time interval and source; preferred contact times, quiet hours and contact frequency.
- Task-specific acceptance and an explicitly permitted backup order. General willingness is not acceptance of a particular visit. Nonresponse is unresolved; another relative is not an automatic fallback.
- Who can change each field and who can see it. A family member can update their own availability; sharing private resident information and acting on their behalf require their respective authority.

Keep physical help, administrative responsibility and financial permission distinct. Allow people to decline, change availability or leave the support network; cancel their pending contact work and reopen affected duties without erasing valid completed evidence.

Evaluate availability for the duty's actual date/time, not merely the current day. Unknown future availability is not a confirmed planning fact. An identified person's explicit acceptance of a clearly dated duty can itself supply task-specific availability when no known conflict exists; avoid requiring a redundant general-availability declaration. A known conflicting declaration must be resolved rather than silently ignored.

## 2. Durable memory

The useful memory is established context that removes repeated explanation:

| Kind | Examples | Treatment |
| --- | --- | --- |
| Person and household facts | Preferred name/language, usual routine, chosen contact pace, reported item location, supplied home constraints | Store who supplied it, when it was recorded, when it applies, its audience and whether it is current, stale, disputed or superseded. |
| Preferences and prior outcomes | Morning deliveries preferred; a storage change was tried and the resident said it did not help | Preserve the report and its scope. A one-time choice does not silently become a permanent preference. |
| Active obligations | Visit date, pickup owner, pending documents, promised follow-up | Keep these in the existing task system; memory references their IDs rather than creating another status copy. |
| Execution history | Requested, accepted, acknowledged, delivered, declined or cancelled | Preserve the actor/tool and evidence reference. An agent's summary cannot establish a physical outcome. |

A minimal new memory record needs an ID, subject person/household ID, fact type/value, source reference and actor, recorded/effective time, allowed audience, status and revision/supersession link. Reuse existing fields where they already cover the need. Permissions remain typed, validated grants, never facts inferred from conversation.

On input, identify the speaker and household, ground any extracted update in that input, validate their authority, and apply a scoped update through the normal revision boundary. Clear self-reported preferences can be saved without asking the same question again. Ambiguous statements and conflicting sources stay unresolved until clarified; preserve the conflict rather than using the last message as automatic truth.

Before each action, retrieve only relevant, permitted, current facts plus the affected task state. Apply filtering before model context is built, including summaries and conversation history. An imported document or retrieved memory cannot issue tool instructions or grant itself authority.

People need an understandable way to inspect, correct and remove remembered information. Removal must also invalidate derived summaries and search copies; backup retention and any minimal audit retention must be explicit. Keep private material out of routine diagnostic logs and exported family views.

## 3. Layers for ongoing autonomous coordination

| Layer | Responsibility |
| --- | --- |
| Identity and permissions | Establish who is speaking and which household, facts, duties, tools and spending limits they may access. Recheck at execution, including after permission changes. |
| Event intake | Turn configured incoming messages, source updates and due reminders into identified events. Preserve source times and deduplicate repeated input. |
| Context and planning | Combine relevant memory, family capacity and the existing plan; choose the next permitted step and identify its dependencies. Replan when a relevant fact changes. |
| Durable execution | Persist work and due times, resume after restart, limit each run and retry safely. Keep the existing validators between model proposals and effects. |
| Tools and outcome verification | Use authorized messaging/service adapters and record their actual responses. Requested, service-acknowledged, helper-accepted and physically completed remain separate. |
| Follow-up and exception handling | Wake at an agreed time or meaningful event; respect quiet hours, cancellation, bounded reminders and named escalation rules. Stop when waiting for a person or missing authority. |
| Operations and evaluation | Show failed connections, overdue duties and uncertain action results; provide pause/stop, activity history and recovery. Measure repeated questions, interruptions and unresolved outcomes by person. |

The operating loop is: receive event → retrieve scoped context → choose next step → validate → execute → verify result → update task/memory → schedule the next permitted check. Ordinary waiting should not consume a continuous model loop.

Assign a stable ID to each intended external action before attempting it. A retry uses that same ID when the destination supports duplicate prevention. If delivery succeeded but the process crashed before saving the receipt, reconcile with the service; where that is impossible, preserve an uncertain result instead of blindly sending again. Do not promise exactly-once delivery from a local snapshot alone. [AWS's retry design guidance](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) explains why caller-supplied request identifiers matter.

For the local demo, reuse the current process, bounded runner, clock/reminders and save mechanisms. Introduce transactional storage only where durable scheduling or concurrent effects require atomic updates that the current mechanism cannot provide; Python already includes SQLite. A new agent framework, queue service or multi-agent hierarchy is not a prerequisite.

## 4. Layers for a family-installed system

Start with a local Mac installation because the current Messages adapter uses the signed-in Mac's Messages database and automation. A container by itself does not supply that native connection. A later hosted coordinator would still need an explicitly designed, permissioned channel connection.

1. **Guided setup:** create the household; invite and verify people; establish sharing, standing permissions, availability and backups; connect only the chosen channels. Explain which data leaves the device for model calls.
2. **Portable configuration:** choose an available model/runtime and credential source; remove assumptions about this developer's application path and account. Check actual inference and channel capabilities separately, with explicit model and spending limits.
3. **Reliable local service:** explicit start/stop, restart after reboot, durable work state, connection status and visible paused/failed states. Persist real due timestamps with the household timezone; waking after downtime rechecks current facts and permission before acting.
4. **Private multi-person access:** authenticated sessions or verified channel identities, per-household authorization, protected secrets and encrypted transport for remote access. Never expose the current demo's role selector as a shared family login. [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) supports default denial and permission checks on every request.
5. **Maintenance and recovery:** versioned data migrations, backup/restore, tested updates and rollback, data export/removal, redacted diagnostics and clear ownership when the household administrator changes.

Self-hosting does not imply offline operation: the current conversation route sends selected context to a remote model. An offline model is a separate configuration with its own capability evaluation.

## First coordinated delivery and acceptance

Build the continuity slice inside the existing fictional household before expanding deployment infrastructure:

- Record a resident's preference and two named helpers' time-bounded availability; reuse them in a later request without repeated entry.
- Restart, then show the same permitted memory and pending duties in both channels without replaying effects.
- Change a visit: retain unrelated preferences, invalidate only affected travel acceptance, and ask an eligible permitted backup only for the reopened duty. Physical completion still requires evidence.
- Correct or remove a remembered fact; ensure a subsequent model context uses the correction and does not retain the removed value in a derived summary.
- Exercise a private resident fact and a second household: neither another helper's context nor another household may receive it. Verify read and mutation boundaries separately.
- Exercise duplicate input, a helper declining, revoked permission, an expired availability window, an unanswered reminder and restart around an uncertain send. None may silently become acceptance or duplicate fulfillment.

Before claiming family-installable operation, run setup, inference, restart, backup/restore and a specifically authorized channel round trip on a clean second-machine environment. Report each missing capability separately. Compare setup plus repeat-use effort and unpaid work by person; no time-saving claim follows from saving memory alone.

Ownership: central owns priority and acceptance; the existing integration lead owns the shared roster/memory contract and persistence; its service owner integrates filtered context, execution and setup; its interface owner exposes family/member changes and exceptions. Retain existing file ownership and publish the shared contract before coordinated edits. This handoff introduces no new independent implementation team.
