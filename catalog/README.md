# Online products and local support

[Back to CareAnchor](../README.md)

The catalog connects a stated everyday task with a sourced candidate and the work needed to evaluate, obtain and set it up. Age alone is not a matching criterion. Local references cover San Francisco; online records use U.S. supplier sources, with address-specific shipping unverified.

## Source records

[online-products.json](online-products.json) holds product identities, source and manual links, checked dates, price conditions, specifications, limitations and setup tasks. [real_world.py](../careanchor/real_world.py) owns the combined catalog and matching categories.

Preserve conflicts between product pages, variants and manuals. A listed price does not establish stock, a delivered total, compatibility or affordable fulfillment. Suggested fit checks and setup tasks are proposed work, not evidence that a person used the product successfully.

## Matching boundaries

- Match the person's stated task and requested channel; do not infer a diagnosis or claim personal fit or clinical efficacy.
- Keep item price separate from the unknown payable total and delivery or setup work.
- Preserve `assessment_required` flags and manufacturer-directed review and installation requirements. An unmeasured home illustration cannot clear them.
- Keep a candidate, request, provider acceptance, purchase, arrival, setup and resident acceptance separate. Catalog lookup initiates none of those actions.

## Updating records

Review the exact variant page and manual, retain conflicting facts, and update the record's `checked_at`. Recheck availability, destination eligibility, total cost and returns before an actual purchase proposal. When adding a category, update its definition in [real_world.py](../careanchor/real_world.py); the API supplies its label to the interface.

Run `python3 -m tests.test_real_world` from the repository root after catalog changes.
