# Online products and local support

The catalog pairs a resident's stated task with a sourced candidate and the work needed to evaluate, obtain, and set it up. Age alone is not a matching criterion. SF remains the local-service area; online products come from U.S. manufacturer stores, with address-specific shipping unverified.

The first online release contains ten products: a jar opener, sock aid, button/zipper hook, reacher, magnifier, accessible landline phone, day/date clock, motion light, shower chair, and fixed grab bar. The six existing SF product, store, and support entries remain available. This is a small reviewed selection, not exhaustive market coverage or a ranking of best products.

## Evidence in each record

`online-products.json` records the exact product/model, official source and manual links, checked date, published price conditions and specifications, fit checks, limitations, and setup tasks. Product facts come from the cited supplier sources. Fit checks and setup tasks are proposed coordination work; they are not evidence that a person tried the item successfully.

Conflicts remain visible: the magnifier's page and manual disagree on included batteries; the reacher has variant-dependent pricing; some pages contain both sold-out and add-to-cart text. The bathroom records preserve differences between marketing and detailed instructions about loads and mounting. Do not erase these qualifications when displaying or summarizing a record.

## Matching and coordination

- Match explicit task categories and online/local channel. The current matcher does not calculate personal fit, compare clinical outcomes, rank efficacy, or infer a diagnosis.
- Show the listed-item budget comparison separately from the unknown payable total. A budget above the item price does not establish stock, delivery, assembly, subscription cost, or affordable fulfillment.
- Ordinary aids need relevant compatibility checks: the user's jars or garments, grip, reading distance, phone line, power, or preferred placement.
- The shower chair and fixed grab bar remain `assessment_required`, regardless of budget. Follow their manufacturer-directed individual review and installation requirements; an unmeasured sketch cannot clear them. This is specific to those products, not a blanket medical-approval requirement for household goods.
- Keep request, provider acceptance, purchase, arrival, setup, and resident acceptance separate. This catalog initiates none of them. A phone compatibility check or delivery-plus-assembly arrangement is future coordination work, not a completed action.

The [National Institute on Aging's room-by-room guidance](https://www.nia.nih.gov/health/falls-and-falls-prevention/preventing-falls-home-room-room) provides general context for home assessment; it does not endorse the catalog's products. No independent benefit, safety, time-saving, or household-usability study has been performed for these records.

## First field test

Recruit three willing older adults, each with one recent everyday task they want to improve. Start with an ordinary aid such as the jar opener or button hook; the bathroom products retain their separate assessment requirements.

1. Observe the current task and workaround. Agree on the person's desired result, acceptable effort, budget, and help before selecting a candidate.
2. Check the actual object, garment, room, or connection; then confirm the exact variant, delivered total, delivery date, return terms, and who would handle setup. Record any failed match and its reason.
3. With explicit purchase and trial consent, observe the same task after setup. Record completion, time, difficulty, and every intervention by another person. A refusal or abandoned trial is evidence, not a missing success.
4. Check again after a week: did the person choose to use it, did it meet the agreed result, and what coordination remained? Reject or revise that match if it misses the agreed result, exceeds the budget, requires unwanted help, or the resident does not want it.

Keep source verification, ordering/delivery, individual usefulness, and willingness to pay as separate outcomes. Three trials can expose bad matches; they do not establish general efficacy or market demand. No participants, purchases, or trials have been completed by creating this catalog.

## Review and update

Before refreshing a record, open its exact product/variant page and applicable manual, preserve conflicting facts, and update its own `checked_at`. Recheck current stock, destination eligibility, payable total and returns before proposing an actual purchase. Run `python3 test_real_world.py` after catalog changes. Adding a task category also requires adding its label to `NEEDS` in `real_world.py`; the API returns labels to the interface.
