# U.S. household planning and coordination simulation

## Outcome

Build a playable week in the life of U.S. older-adult households, where an assistant maintains a whole plan across home needs, appointments, paperwork, supplies, transport, and chosen community activities. The primary outcome is less unpaid family care and coordination time, beginning with administrative work. People establish preferences and bounded permissions; the assistant completes permitted simulated administration and asks about consequential exceptions. Changes propagate through affected arrangements, and every claimed outcome has evidence.

This is the expanded simulation build authorized by the user. The target population is the United States, not the user's own family. The primary objective and resident-led principles remain in [PROJECT.md](PROJECT.md#direction). This document owns the expansion sequence; PROJECT.md owns the current implementation contract.

## Population and setting

Start with three editable, fictional household situations: an older adult living alone with nearby support; a couple sharing household responsibilities; and an older adult with a remote family helper and limited local availability. Vary age band, household composition, urban/suburban/rural setting, transport options, preferred language and interaction style, support availability, and explicitly declared task constraints. These attributes are independent configuration choices; age or geography must not imply incapacity, personality, or medical conditions.

Use age 65+ as the initial population definition. Census ACS [B09020](https://api.census.gov/data/2024/acs/acs1/groups/B09020.html) describes living arrangements for this population, while [S0103](https://api.census.gov/data/2024/acs/acs1/subject/groups/S0103.html) supplies additional population characteristics. These are sources for scenario dimensions and later aggregate calibration. The first three cases are a coverage sample, with no national weights or claim of representativeness. A later calibrated cohort must document source vintage, geography, joint distributions, missing fields, and validation separately from simulation results.

Reuse the current original and sketch-derived Blender scenes as illustrative environments. The supplied sketch does not establish a typical U.S. dwelling; its confirmed facts and unknown measurements remain intact. A household selector changes the simulated people, constraints, and week without relabeling the physical asset's provenance.

For the replay environment, model local opportunities and services as explicit fictional fixtures with availability, deadlines, capacity, costs, and response rules. The user has additionally selected San Francisco for real public store and service discovery, as scoped below. The [ACL Eldercare Locator](https://eldercare.acl.gov/home) is a verified service-discovery entry point, not evidence that any particular service is available or booked. Public options and synthetic replay fixtures must remain distinguishable.

## San Francisco public store and service discovery

Connect the household's stated need and equipment requirements to source-checked public product and provider options in San Francisco. Each option carries a source link, checked date, relevant published specifications or service coverage, and explicit unknowns for dimensions, stock, price or quote, delivery, installation, eligibility, and appointment capacity. A public listing supports discovery; it does not establish suitability or an available slot. Match only against declared facts and requirements, and expose missing checks before preparing a sourcing or handoff step.

The assessment task (`01a08263-2b9c-7050-b2d3-0c84d852b0f0`) owns `real_world.py`, the public catalog/matcher, and its runnable check. The existing build lead integrates it through the existing service and interface owners. The discovery layer was verified in the running demo and browser on 2026-09-08, including sourced matches, budget caveats, and preparation steps. It supersedes fictional-only discovery for San Francisco; it does not change synthetic population or replay outcomes.

The authorized result is linked options and prepared next steps. No actual purchases, bookings, messages, account changes, credentials, or transmission of private household data are included. Public source access is permitted. Real execution remains a separate action requiring its specific authorization.

## One shared plan

Keep a single household plan across domains: people and their permissions; time-bound commitments; sourced observations; supplies and reported locations; tasks and their dependencies; offers from simulated services; and an event history with outcome evidence. Plan states must distinguish an intended action, a request, an accepted arrangement, and actual completion.

The assistant can prepare paperwork lists, update the simulated calendar, find conflicts, request simulated help, consolidate tasks, and perform fictional transactions within standing permissions. New commitments beyond those permissions, changes to valued plans, and unavailable alternatives produce one grouped decision where possible. A helper controls their own availability. Physical delivery or preparation still needs observation or an authorized person's report.

Use the existing simulation state, event endpoints, scene overlays, and Astra connection. Start with explicit scheduling and dependency rules. Astra can propose or invoke bounded simulation actions through validation; it cannot make an unsupported state transition true by saying it happened. Agent roles are responsibilities around a shared plan, not a requirement for separate autonomous processes. The build lead chooses the minimum code changes after tracing current callers.

## Connected week scenarios

All scenarios operate on the same week. Fixture times, prices, readings, paperwork, and service responses are fictional and labeled accordingly.

| Scenario | Disruption and assistant work | Remaining choice and completion evidence |
| --- | --- | --- |
| Appointment and weekly plan | A clinic moves an appointment into a chosen activity. Identify the conflict, invalidate the old ride, preserve applicable paperwork, and compare supplied mock alternatives. | Resident decides between valued commitments; mock clinic acknowledgment confirms the selected appointment. Transport remains pending until separately accepted. |
| Transport and shared support | The usual driver declines. Request an already-permitted backup, including return travel; update related preparation times. | The backup accepts their own commitment for the current appointment version. If nobody is available, expose the unresolved exception instead of manufacturing a ride. |
| Paperwork and home preparation | Required papers were last reported near the entrance but have moved. Retain the checklist, mark the location uncertain, and contact the delegated preparation helper once. | The helper checks and stages the papers, then supplies a report. Reuse that authorized report without demanding duplicate resident confirmation. This establishes preparation, not attendance or clinical sufficiency. |
| Supplies and app tasks | An approved household supply is unavailable. Select a preapproved equivalent within a fictional spending limit and execute the simulated order. | Ask only if the substitution or cost exceeds permission. Keep order acknowledgment, delivery, and placement as separate states; receipt does not follow automatically from ordering. |
| Optional community activity | A venue cancels an event. Cancel only its dependent arrangements and offer supplied alternatives fitting declared preferences. | Choosing another event or leaving the time free are valid. Mock cancellation acknowledgment closes the unused booking; unrelated appointment transport remains confirmed. |
| Home comfort and observations | A resident reports that a frequently used item is awkward to reach, or a simulated home-device reading becomes unavailable. Clarify the specific need; compare existing-storage or sample-equipment options, or arrange a permitted device check. | The resident chooses an option; a helper reports the physical change and the resident reports whether it helped. Sensor values remain labeled observations, with no invented diagnosis, clinical recommendation, or measured safety claim. |

The same event sequence should play differently under different support capacity, preferences, and permissions. It must not force every household into the same plan or make attendance, purchasing, and accepting help compulsory.

For the home-comfort scenario, assess one bounded before/after adaptation in the existing house with a linked illustrative equipment card and order-preparation step. Show required specifications and missing measurements; do not claim verified fit, live availability, installed cost, or a real order from the sketch. Keep selection, ordering, delivery, and installation/placement distinct. The existing build lead coordinates this addition with the original Blender and interface owners. [The market and positioning brief](YC-AGING-COMPARISON.md) provides context without adding a commercial gate.

## Build checkpoints and ownership

| Checkpoint | Deliverable | Acceptance |
| --- | --- | --- |
| 0. Preserve the current game | Finish corrected-sketch render/hotspot alignment and its browser walkthrough. | Existing outing, privacy, stale-state, and live-Astra checks remain verified. |
| 1. Household week | Editable fictional household profiles, one week of shared commitments/tasks, and linked scenario events using the existing home experience. | Switching profiles does not mix private state. A moved appointment changes only affected commitments; the week can be reset and replayed. |
| 2. Delegated coordination | Standing permissions plus bounded agent execution in the simulated environment; named human/helper roles and grouped exception decisions. | Permitted routine actions require no repeated resident approval. Out-of-scope actions remain pending. Helper refusal, revocation, stale data, and duplicate attempts are handled without false completion. |
| 3. Complete inner/outer loop | Integrate all six connected scenarios with visible actions, state changes, and evidence. | A full week reaches explainable completed or unresolved outcomes; home changes and outside plans affect one another. No fake real-world action is reported. |
| 4. Household comparison | Replay the same disruptions across the three configurable cases and compare manual versus assisted administration. | Report actual scenario results by participant and household, including setup and corrections. No national-effectiveness claim follows from the demonstration. |

Central coordination owns this plan, scope decisions, and cross-task consistency. **Find previous AI for aging idea** remains the sole build/integration lead and assigns its existing interface, service, and Blender owners. **Regroup aging population AI idea** reviews scenario coherence and the burden comparison without imposing business-validation gates. Do not duplicate code ownership or overwrite the current scene work.

Implementation can proceed through these checkpoints without another routine approval. Actual messages, purchases, bookings, private account/data connections, sensors, and clinical actions are not authorized by this simulation expansion. Each is a separate future real-world connection.

## Demonstrating less administration

Run the same fictional week manually and with the assistant, using identical facts, disruptions, service timing, alternatives, and physical-help requirements. Count administrative decisions, repeated questions, re-entry, interruptions, corrections, and unresolved dependencies by participant. These are scripted interaction counts, not measurements of time or cognitive burden. Count active time only when measured in a participant walkthrough; do not assign imaginary minutes saved to simulated steps.

The eventual primary measure is net unpaid coordination minutes per household, task, or week, including setup, confirmations, chasing, corrections, and exception handling. Identify unpaid family/helper work separately from paid service work and resident effort, while reporting all participants so transferred work remains visible. Hands-on care time and wanted human contact are separate outcomes; neither is inferred from fewer interface interactions.

Show first-week totals including setup, then repeat-week totals separately. Exclude camera movement, scenario injection, reset, and other game controls; substantive resident choices and coordination replies still count. The claim fails for a scenario if setup or supervision erases the savings, work merely shifts to another person, or the assistant reduces interaction counts by leaving work unresolved or acting without permission. Unsupported completion and unauthorized commitments must be zero.

Current replay evidence (2026-09-08): nearby-support and couple cases record 19 manual versus 18 assisted interactions including setup; remote-support records 14 in both with unresolved work. Family counts are unchanged. Accounting currently uses resident/family role buckets, not individual people; both modes begin with identified tasks, and bundled setup counts as one event. This demonstrates a small batching difference, with no demonstrated family interaction or unpaid-time reduction. Reading, discovery effort, decision difficulty, and movement of work between people within a role remain unmeasured.

## Beyond the hackathon

After the simulation is complete, progress to permissioned real workflows in a chosen U.S. locality, then validated cohorts. Healthcare records and sensors can inform the plan when their meanings, permissions, and handling are defined. Government planning is a proposed later use of calibrated scenario comparisons; home-robot evaluation and training require physical tasks, suitable simulation dynamics, and real-world validation. Neither capability is implied by the current visual game.

MatrAIx remains an optional persona-testing candidate; its public dataset is not required for this build and has separate research-only terms. NHATS/NSOC research documentation may inform later study design, but its participant files are not input to this prototype: their [conditions of use](https://www.nhats.org/conditions-of-use) restrict sharing and uploads to public AI platforms. Use authored fictional fixtures and public aggregate sources here.

Sources checked: 2026-09-08. This is a build plan, not a record that the expansion has already shipped.
