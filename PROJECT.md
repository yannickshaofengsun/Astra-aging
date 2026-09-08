# CareAnchor — first playable household

Build a local household simulation with an editable Blender home and a game-like experience for exploring everyday activities and optional local support. GPT-6-Astra supplies the live conversation. Explicit state rules govern confirmations and privacy; the appointment-change scenario is the first implemented flow.

The ultimate product vision is an ongoing coordination service that helps older adults live at home while reducing the organizing, repeated explanation and chasing done by residents and families. The current task is a usable, understandable local hackathon demonstration of that service. The user explicitly said hosted-service implementation is unnecessary for this demo. Do not add hosting, billing or production infrastructure to the current build; explain the vision through completed interactions and clear results.

## Direction

The primary objective is to reduce unpaid family care and coordination time, so family members can spend more time working or doing other things. Start with administration: remembering requirements, repeated explanations or data entry, appointments and paperwork, sourcing equipment, arranging help, chasing responses, checking completion, and recovering when plans change. Judge future features by net unpaid time removed, including setup, review, correction, and exception handling. Do not achieve an apparent saving by shifting chores onto the resident or another unpaid helper, leaving needs unresolved, or removing wanted human contact. The inner and outer systems organize the context needed for this objective.

Home adaptations and equipment may also reduce hands-on help, but this is a future measured outcome. The current simulation can compare manual steps and interruptions; it cannot establish hours of care saved without measured participant walkthroughs.

The resident goal is a better daily life: comfort, independence, chosen activities, and familiar routines. The user clarified that living better is the purpose; longevity is not an outcome claimed by this build. Potential AI/robotics-lab offerings are a secondary opportunity and do not replace the household mission.

Support must continue through gradual changes in daily life. Needs, preferences, home arrangements, and available help can evolve unevenly over weeks or months; adaptation is not a prescribed lifestyle-change program. Preserve what matters to the resident, remember what was tried and whether it helped, and allow small changes to be kept, adjusted, deferred, or reversed.

Companionship and continuity sit alongside practical coordination. The assistant should maintain familiar context, check in at an agreed pace, and help sustain wanted contact with family, friends, neighbors, and helpers. A completed task is one event in that ongoing relationship. Keep the many logistical details in the shared plan and surface the next meaningful choice or unresolved exception, so the resident and family do not have to manage the system's complexity. This is the product direction; the current episode-based demonstration does not yet establish sustained support or reduced burden over time.

The working product framing is a home and care concierge, including adapting the existing home and helping arrange suitable equipment. Lower insurers' future claims and care costs is a longer-term outcome hypothesis, not a demonstrated capability. [The YC comparison and positioning brief](YC-AGING-COMPARISON.md) records relevant services and evidence. Improving an established category is a valid direction; category novelty is not a requirement.

Two agent workflows are core requested functionality: assess supplied house information and create/update a proposed 3D arrangement with equipment options, replacement questions and an itemized overall cost/assessment; retrieve hospital information and coordinate visits, paperwork, transport, in-hospital accompaniment and relevant-person updates. Existing-prescription refill administration is also core nonclinical coordination. Do not reduce the product to household-supply ordering or defer these workflows by labeling all healthcare connections as later. Missing sources, access, measurements or credentials are explicit dependencies for particular actions, not reasons to remove the workflow from scope. The user clarified that "overall date" means overall cost and assessment information.

Home assessment and remodeling are episodic: initial setup, then revisits when needs, equipment or the home change. The everyday service is natural conversation, reminders tied to existing plans, follow-up and coordination among the resident, family and helpers. The resident interacts through actual Apple Messages. Other household members use the existing interface as a coordination workspace reflecting the same plan: see relevant changes, accept their own responsibilities and handle exceptions. It also retains house simulation and 3D/cost review. The resident must not need to operate that interface, and family members must not have to supervise every agent step. Messages, voice/dictated text and the household interface share the same facts and actions. Actual messaging is limited to explicitly configured test participants and requires verified local access; a simulated thread is not proof of an Apple Messages connection.

Physical output is also a requested interaction mode: a monthly printed family update with contributed photos, short news and ordinary activities from the rest of the family. CareAnchor coordinates contributions, prepares a readable edition and follows through on printing and delivery so the resident can enjoy it around the home without opening a phone. Preserve contributors' voices and the resident's preferences; do not turn it into a care report. The hackathon uses fictional contributions and clearly labeled photo placeholders until specific images are supplied. A print-ready file, accepted printing task, printed copy and delivered copy are separate outcomes. No real mailing order, printer job or family outreach is implied by this feature request.

The user subsequently clarified that the PDF is a side feature. Complete the app's actual iMessage interaction and household-dashboard task-completion loop first, including changed plans and accurate completion evidence. Keep the printed example and landed optional code without allowing further PDF work to delay that main demonstration.

The target population is U.S. older-adult households and their support networks. The user has authorized expansion from the first game into whole-household planning and coordination simulation. [The U.S. simulation plan](US-SIMULATION-PLAN.md) owns that expansion, its fictional household cases, and verification checkpoints; the contract below describes the current implementation until the build lead updates it.

Residents know their routines and community. Preserve that knowledge and their choices; introduce new equipment, support, and local events as optional opportunities to live better locally. The simulation must not frame success as habit change, compliance, or persuading residents to accept help.

The household simulation is intended to become part of a physical AI environment where home robots and other agents could later be trained and evaluated. Supporting older adults at home is the first use case and gives the simulated world concrete human needs, tasks, and constraints.

The current build is the first step: an editable home scene and a synthetic family-coordination scenario. The longer-term training ambition does not expand this build into a robotics platform. Robot control, physical interaction, and training infrastructure remain future work; training usefulness and transfer to real homes are unverified.

## Inner and outer systems

The product connects two systems operating together; requested capability and verified connections must remain distinct:

| System | Information and work |
| --- | --- |
| Inside the home | Layout, steps and movement, heart-rate readings, permissioned home recordings, supply availability, and residents' own reports of comfort and difficulties. |
| Outside the home | Hospital appointments and calendars, paperwork, local activities and support, and completing tasks in apps or services. |

The connection is shared, permissioned context that turns observations and existing care information into optional equipment, activity, or support suggestions. Preserve the source, time, uncertainty, and permitted audience of each fact. Keep measurements, resident reports, existing clinician instructions, model interpretations, and simulated assumptions distinguishable. Ask residents about comfort rather than treating sensor activity as a comfort score.

Close the loop: observation or request → contextual interpretation → optional next step → resident choice → named person or authorized agent accepts the task → confirmed outcome → updated context. Execution may belong to the resident, a caregiver, family member, or GPT agent. Preserve that person's or agent's actual scope of permission; a suggestion or attempted tool action is not completion. Share only the information needed for the accepted task, and let changed facts reopen affected plans.

Each suggestion should explain its practical relevance, what remains uncertain, and the next action. The system can organize observations and accurately relay existing instructions, but must not generate medical advice, clinical interpretations, diagnoses, treatment or dosing recommendations, or medically consequential equipment/activity recommendations. Sending AI-generated medical advice for later review does not bring it into scope. Resident choice, refusal, and existing routines remain central.

Seamless execution should use standing preferences and permissions for routine work, with intervention for meaningful choices, unresolved conflicts, failures, or actions beyond the agreed scope. Capture confirmations from existing evidence where possible; do not make the family maintain a parallel task log or approve every small step. Equipment and activity suggestions are useful only when they solve a resident-chosen need without creating more administrative work. The current demo's explicit confirmation controls are a prototype boundary, not a requirement that every future action needs another prompt.

The expanded simulation models these information-and-action loops with explicit fictional inputs and services, as scoped in the U.S. simulation plan. Public store/service discovery for San Francisco and the U.S. online equipment catalog may use real sourced listings. Hospital coordination must also support source-stamped supplied notices or records and authorized information retrieval when the chosen source is accessible. The current demo has no verified private hospital/health-record or transactional connection; report the missing access specifically, without implying live event monitoring. Sensors and continuous recordings likewise require a defined input connection. Real transactions, fulfillment and external messages need their specific authorization; simulation evidence must not be presented as those actions.

## Hackathon priority

Build and demonstrate the household simulations. Business-model selection, pricing, paid pilots, and commercial validation are outside this hackathon's scope and must not gate the simulation work. Continue the authorized home and daily-routine scenarios, keeping observed household facts distinct from assumptions and simulated results.

The user's strict anti-project exclusions apply to every new scenario: no AI mental-health advisor, basic RAG application, basic Streamlit application, education chatbot, job application screener, nutrition coach, personality analyzer, AI-generated medical advice, dashboard as the main feature, or sports analyzer/coach. The earlier image-analyzer exclusion does not prohibit the user's later explicit request to interpret supplied house images/plans as part of creating a 3D model and completing an equipment/coordination workflow; do not turn that component into a standalone image-analyzer product. Everyday interaction is messaging about coordinated household actions; the visual home supports assessment and simulation. Existing-prescription refill administration handles logistics; nutrition and medication decisions are excluded. The [current feature plan](US-SIMULATION-PLAN.md#current-feature-delivery-plan) owns delivery and acceptance; additions are not implemented merely because they are described there.

## Requested hackathon output

- Actual Apple Messages as the daily interaction channel for selected test participants, with natural requests, contextual replies and relevant updates connected to the same household action system. Preserve the web experience for simulation, setup and reviewing proposals. Receive, execute and reply must be verified separately; no real message is sent without a concrete authorized recipient scope.
- An editable Blender home based on the supplied hand-drawn plan, with approximate geometry and unmeasured dimensions identified. Home photographs, measured maps, and house-design files are future input routes.
- A game-like household simulation with visible choices, changes in scenario state, outcomes, and replay. Projected clickable markers and an animated story avatar implement the scene interaction; movement is illustrative, with no physical path simulation.
- Optional local activities and support connected to a resident-chosen scenario. Start with a bounded, clearly labeled fictional example when no locality or verified source is available. Declining an opportunity or keeping an existing routine is a valid choice. Real event coverage, availability, and bookings must not be implied by sample data.

The build/integration lead owns delivery of these extensions through the existing workstream owners. Treat requested output separately from verified current capability; update the implementation contract and README as integration is completed.

## Coordination

The user owns direction and final decisions. The central coordination task (`01a0821f-4f9a-7b12-a7b8-a9747fd76124`) consolidates work and scope decisions. **Find previous AI for aging idea** remains the build/integration lead; **Regroup aging population AI idea** owns product-direction analysis. Implementation ownership below remains in place.

## First scenario

An appointment moves from Tuesday to Thursday. Transport becomes unconfirmed. A family member can accept the new pickup. The resident can ask where their documents were last recorded; a simulated move makes that information stale until reconfirmed. Only the resident sees the private appointment reason. No real messages, bookings, medical advice, or safety claims.

## Ownership

- `blender/`, `assets/home.*`, `assets/sketch-home.*`, `assets/sketch-layout.json`, `assets/game-hotspots.json`: original Blender subagent. Preserve the original synthetic scene. Sketch assets are approximate and unmeasured; source photos are not browser-served.
- `simulation.py`, `test_simulation.py`, `test_week.py`, project docs: build/integration lead. `week.py`: household-week subagent; `comparison.py` and `test_comparison.py`: replay subagent.
- `web/index.html`: dedicated Codex interface task.
- `server.py`, `astra_bridge.py`, `test_server.py`: dedicated Codex Astra service task.
- `.coordination/paperclip.json`: Paperclip subagent; coordinator owns later updates.

## Integration contract

Python standard library only. Run `python3 server.py` on `127.0.0.1:8765`. No frontend dependencies. The selected home's render and downloads come from `state.home.image`, `.blend` and `.glb`, restricted to `/assets/home.*` or `/assets/sketch-home.*`. The sketch selector also changes the house context supplied to Astra. Model-facing context whitelists room labels/uses, user-confirmed facts, assumptions and unknowns; no source image or local source path is included. The appointment/ride/document scenario stays fictional with either home selected. Reset preserves the selected home; changing homes clears both conversations.

`simulation.py` exports `Household`, `InvalidAction`:

- `Household()` creates synthetic initial state.
- `view(role)` returns the JSON-safe view below, role is exactly `resident` or `family`.
- `event(action, role, expected_revision=None)` mutates state and returns `view(role)`; actions: `reschedule`, `confirm_ride`, `decline_ride`, `move_documents`, `confirm_documents`, `reset`, `select_demo`, `select_sketch`. Confirm/decline actions REQUIRE the current integer revision to prevent stale acceptance; family alone can confirm/decline a ride. Resident alone can confirm document location. Reschedule, move, reset, and house selection are explicit scenario controls, not AI actions.

View shape:

```
{
  "role": "resident", "revision": 0,
  "appointment": {"day":"Tuesday", "date":"2026-09-15", "time":"10:00", "pickup":"09:15", "reason":"Private follow-up — synthetic example"},
  "transport": {"status":"confirmed", "person":"Alex", "for_date":"2026-09-15"},
  "documents": {"location":"Entrance shelf", "status":"confirmed", "recorded_at":"Tuesday, 08:00"},
  "plan_status":"ready", "next_steps":[],
  "activity":[{"text":"...", "revision":0}],
  "notice":"Fictional scenario. Live chat sends the selected role and house context to OpenAI."
}
```

Family view OMITS appointment.reason entirely. `plan_status` is `ready` or `needs_attention`. `next_steps` is an array of plain strings. Document locations are household logistical information, visible to both roles. `documents.status` is `confirmed` or `last_known`. `transport.status` is `confirmed`, `needs_confirmation`, or `declined`. A stale document location must never be represented as current. Reset restores initial data while advancing revision monotonically. Expose no secret/internal actual document location to the family or model until resident confirmation.

HTTP endpoints:

- `GET /api/state?role=resident|family` returns view directly.
- `POST /api/event` body `{role, action, revision}` returns updated view directly. Server passes revision to `Household.event` as expected_revision. Browser sends the revision of its current displayed view.
- `POST /api/chat` body `{role, message, history}`; history is at most 12 `{role:'user'|'assistant', content:string}` messages for THIS selected channel. Response `{reply, engine:'gpt-6-astra', revision}`. Astra is read-only: it explains current plan, asks about next steps, and directs people to explicit confirmation buttons. Never fabricates actions/completion. Bridge passes ONLY selected role's view to the model. If revision changed during generation, reject stale answer or clearly regenerate from current state.
- `GET /api/health` reports local service/model configuration without claiming inference success.
- Errors use appropriate HTTP codes and `{error:string}`; model failures never silently switch to canned text.

Role tabs simulate perspectives; this local synthetic demo has no authentication and is NOT a production privacy boundary. Server binds loopback, validates Host/Origin and request sizes, serves only intended web/assets files, rejects invalid role/action. Don't expose project internals, runtime, credentials, or logs as static files.

## Interface

Polished, warm, accessible desktop layout: title and synthetic/live labels, Blender scene, compact current plan, Resident / Family conversation tabs with independent message histories, readable text input and send/loading/error states. Scenario controls: Move appointment to Thursday; Move documents; Reset. Confirmation buttons: family confirms/declines ride; resident confirms documents. Enter submits, keyboard controls work, app state loads from server. Do not add dashboards, medical advice, fake real-world integration, or placeholder AI replies. Clearly distinguish scenario controls from actions that a person confirms.

## Verification

Run core assertions, HTTP/privacy checks, an actual Astra response, Blender background build/render, and browser walkthrough of reschedule → pending ride → family acceptance. Record limitations. Paperclip tracks project and real worker status; synchronization is coordinator-managed, not an autonomous Paperclip/Codex integration.

## Playable local-activity loop

`view.outing` carries a clearly fictional community-garden activity, resident choice, ordered preparation steps, optional companion-support state, projected hotspots, and an outcome/message. This is an offered possibility; keeping the resident's usual routine is an equally valid outcome, with no failure or compliance score.

Existing revision-bearing `/api/event` actions: resident `join_activity`, `keep_routine`, `restart_game`, `request_support`, `game_invitation`, `game_bag`, `game_entrance`; family `confirm_support`. Preparation clicks must proceed invitation → bag → entrance. Requested support remains unresolved until explicitly accepted at the current revision. Completion without requested support is allowed. Reset/home changes reset the outing.

`outing.outcome` is `choose`, `staying_home`, `preparing`, `waiting_for_support`, or `ready`; `next_hotspot` is the next step or null. `hotspots` contain normalized top-left image coordinates exported through actual saved Blender cameras. UI overlays native keyboard-accessible buttons and an avatar on the matching intrinsic image aspect; avatar movement is a visual transition, with no claim of measured navigation or collision simulation. Text alternatives cover missing render/hotspots. Game props do not establish actual belongings locations. No real events, reservations, support requests, or geographic/route claims occur.

Acceptance: exercise voluntary decline/replay, ordered preparation, optional support request → pending → family acceptance, both homes' marker alignment, and one grounded live Astra reply. Preserve previous appointment/privacy checks.

## Household-week implementation contract

`Household` now owns `WeekPlan`; the week uses the same appointment, transport, and document fields as the existing detail controls. `view.week` exposes the selected fictional profile, independent editable profile fields, standing permissions, commitments/tasks with evidence, role-filtered action controls, exceptions, adaptation preview data, and recorded administration counts. Known document location does not imply staged paperwork; pickup-only confirmation does not imply accepted return travel. The independent Saturday practice story survives weekly activity cancellation.

`POST /api/event` also accepts optional `payload` objects for `week_*` actions. Every weekly action requires the exact current revision, validates its payload and role, and must be supported by the current state. Profile/week reset clears previous household logs. `context_revision` changes on profile/configuration/mode/reset/home changes so both conversations can discard old context. The deterministic `week_run` action performs only permitted fictional administration; it cannot supply a human report. The live chat remains read-only.

`GET /api/comparison` replays three fresh fictional households in manual and assisted modes without changing the active household. Its counts include setup and supervision, distinguish resident/family role buckets from agent execution, and report matched inputs/outcomes, evidence, unresolved work and limitations. Same-role counts do not establish that work has not shifted between individual people. No measured time or family-care saving is inferred.

`GET /api/real-options?need=...&budget_cents=...` returns a bounded curated San Francisco public-source match; the budget is optional, in nonnegative integer cents. The independent assessment task owns `real_world.py` and its check. `state.public_discovery` supplies all five unbudgeted source groups to Astra; a UI budget filter is not a real spending permission. Matches and prepared next-step checklists remain `not_requested`, regardless of any fictional orders. No source photo, private account data, or provider credentials are included.

`assets/sketch-adapted.png` and `.blend` are an optional proposed caddy preview from the same sketch camera. Equipment request preparation, a helper's simulated placement report, and resident feedback remain separate. The generic simulation caddy is not a verified match to a real catalog item.

## Demanding outing mission implementation

`Household.mission` owns one bounded planning rehearsal in `mission.py`. Starting it changes the shared appointment and invalidates its travel, with unavailable primary help, relocated items, and a blocked symbolic main route already present. Community commitments and the separate practice story are preserved. World truth is private; resident/family/coordinator views contain only reported knowledge. A last-known location must first be checked and reported not found before a new observation can locate an item. Location, staging, helper loading, and executor delivery are distinct evidence states.

`view.mission` supplies the current status, elapsed fictional minutes/deadline, current appointment version, observed items/help/routes, robot state, five bounded permissions, current-role controls, event history, unresolved dependencies, and proposal audit. The resident chooses to proceed and controls coordinator, backup-helper, robot-transport, main-route and alternate-route permissions. Family controls name Alex or Morgan explicitly; those remain one simulated family role bucket. Morgan must separately accept help, confirm outbound and return travel for the current appointment, stage documents, and load the bag.

The robot capability is `carry_preloaded_bag`. Route nodes and edges are symbolic game rules; the unmeasured sketch has no confirmed Hall room. A movement step reports progress or a blockage, stops on revoked permission/cancellation/deadline, and never establishes physical clearance. A new observed usable alternate plus permission is required for recovery. Final `ready_to_leave` requires current travel provenance, resident choice, staged/loaded item evidence and delivery before the deadline. It establishes neither attendance nor robot transfer to hardware.

`POST /api/mission/astra` accepts `{role:'resident',revision}`. The service snapshots `Household.coordinator_view()`, asks GPT-6-Astra for one structured `{action,reason}` proposal through the existing bounded CLI connection, then calls `apply_mission_proposal` under the lock. The model never receives private world state, household private appointment reasons, or human/scenario controls. Every proposal is checked again against the current revision, actor, permissions and eligible actions. Response is `{state,proposal,engine}`; accepted actions return 200, stale proposals 409, and other rejected proposals 400. Rejected proposals record an audit but make no operational change. Chat remains read-only, and the older weekly `week_run` remains deterministic.

Every `Household.event` mutation now requires the current integer revision, including reset, home selection and legacy scenario actions. Household reset is resident-controlled. Initial missing return travel can be requested independently of accepted pickup; legacy pickup reconfirmation preserves valid return evidence. Revoking an unrelated permission no longer clears a supply-specific approval.

Canonical `python3 server.py` enables `.runtime/mission-state.json`. `Household(save_path=None)` and `Server(...,save_path=None)` default to isolated unsaved state for tests. Atomic bounded JSON snapshots contain mission plus shared household/week context; schema, fields/types, enums, integrity and mission evidence are validated before adoption. No actions replay during load. Restores advance revisions, and invalid files produce a visible load error with a fresh household. A failed write preserves the old file and reports that the current in-memory state was not saved. Resident `mission_save`/`mission_restore` also use `/api/event` and current revisions. These files are not served or committed.

`mission_evaluation.py` evaluates five authored cases in fresh households without a model call or active-state mutation. The report distinguishes scripted coordinator actions, human reports, waits, deliberate rejection probes, fictional clock values and unresolved outcomes. It is separate from actual GPT action evidence and does not measure family time or physical collision counts. Run the eight `test_*.py` scripts listed in README, plus the evaluator, for reproducible evidence.

Public discovery now supports `channel=all|online|local` and 13 needs, with ten researched U.S. online product records alongside six prior public options. Published specs, fit/setup checks, source conflicts and two assessment-required bathroom options remain explicit. Every option remains `not_requested`; the mission coordinator receives no catalog data and cannot initiate a real transaction. Catalog source/field ownership remains with the assessment task.
