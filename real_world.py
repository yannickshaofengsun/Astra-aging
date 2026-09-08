"""Reviewed public SF options. No live inventory, accounts, requests, or orders."""

from copy import deepcopy


NEEDS = {
    "home_storage": "Organize everyday items at home",
    "household_supplies": "Find household supplies",
    "assembly": "Arrange furniture assembly",
    "everyday_help": "Find help with everyday tasks",
    "community": "Explore community activities",
}
CHECKED_AT = "2026-09-08"

# ponytail: small reviewed catalog; add live provider feeds when access is available.
_OPTIONS = [
    {
        "id": "ikea_nissafors", "kind": "product", "provider": "IKEA",
        "name": "NISSAFORS utility cart, black", "needs": ["home_storage"],
        "url": "https://www.ikea.com/us/en/p/nissafors-utility-cart-black-20399777/",
        "source_urls": ["https://www.ikea.com/us/en/p/nissafors-utility-cart-black-20399777/",
                        "https://www.ikea.com/us/en/stores/san-francisco/"],
        "summary": "An indoor storage option for everyday belongings; assembly is required.",
        "location": "IKEA San Francisco, 945 Market Street; product stock unverified",
        "published_price_cents": 2999,
        "price_note": "Listed item price only, checked September 8. The page also lists a conditional "
                      "$19.99 in-store IKEA Family offer; eligibility and local availability are unverified. "
                      "Tax, delivery, and assembly are not included.",
        "dimensions_in": {"length": 19.875, "width": 11.75, "height": 32.625},
        "unknowns": ["Current local stock and delivery window", "Final total including tax and services",
                     "Measured home clearance, suitable placement, and resident preference"],
        "next_steps": ["Compare measured space and the resident's preference with the listed dimensions.",
                       "Check the exact item, local stock, delivery or pickup, and full price with IKEA.",
                       "Choose who receives and assembles it; only schedule assembly after delivery is confirmed."],
    },
    {
        "id": "home_depot_colma", "kind": "store", "provider": "The Home Depot",
        "name": "Colma II household supplies", "needs": ["household_supplies"],
        "url": "https://www.homedepot.com/l/Colma-II/CA/Colma/94014/639",
        "summary": "Nearby store with storage containers, cleaning supplies, and paper goods. "
                   "Its page describes pickup and conditional delivery services.",
        "location": "Colma, near San Francisco; address-specific delivery unverified",
        "published_price_cents": None,
        "price_note": "No specific item or delivered quote has been selected.",
        "unknowns": ["Exact item and acceptable substitutes", "Item stock and total price",
                     "Delivery coverage, fees, and time window for the destination"],
        "next_steps": ["Choose the exact supply and permitted substitutes.",
                       "Check stock and full pickup or delivery cost for the destination.",
                       "Identify the person receiving or collecting it and record the retailer's acknowledgment."],
    },
    {
        "id": "taskrabbit_assembly", "kind": "service", "provider": "Taskrabbit",
        "name": "San Francisco furniture assembly", "needs": ["assembly"],
        "url": "https://www.taskrabbit.com/locations/san-francisco/assemble-furniture",
        "summary": "A marketplace for furniture assembly. The SF page supports comparing providers "
                   "and supplying product links to define the job.",
        "location": "San Francisco; individual provider coverage unverified",
        "published_price_cents": None,
        "price_note": "Request the task-specific total, minimum hours, and fees; no quote has been obtained.",
        "unknowns": ["Provider availability and acceptance", "Final quote and minimum booking",
                     "Confirmed product delivery and job scope"],
        "next_steps": ["Prepare the exact product link and assembly scope.",
                       "Check a provider's total price and availability after confirmed delivery.",
                       "Record an accepted appointment separately from reported completion."],
    },
    {
        "id": "sf_village", "kind": "service", "provider": "San Francisco Village",
        "name": "Membership and volunteer support", "needs": ["everyday_help"],
        "url": "https://www.sfvillage.org/join/",
        "summary": "Membership includes volunteer requests such as grocery shopping, laundry help, "
                   "and technology troubleshooting. Matching may take a week or more.",
        "location": "San Francisco",
        "eligibility": "SF residents aged 60+; application and staff meeting required.",
        "published_price_cents": None,
        "price_note": "Sliding monthly membership fees are published; these are not a task-specific quote.",
        "unknowns": ["Membership acceptance and applicable fee", "Task scope and volunteer capacity",
                     "Whether the available timing meets the household's need"],
        "next_steps": ["Check residency, age, and the membership process with the organization.",
                       "Describe the requested everyday task and its deadline.",
                       "Wait for a named helper to accept; the listing does not guarantee a match."],
    },
    {
        "id": "clc_community", "kind": "service", "provider": "Community Living Campaign",
        "name": "Community Connectors and Neighborhood Buddies", "needs": ["community"],
        "url": "https://sfcommunityliving.org/programs/neighborhood-networks/",
        "source_urls": ["https://sfcommunityliving.org/programs/neighborhood-networks/",
                        "https://sfcommunityliving.org/events/"],
        "summary": "Neighborhood activities and social connections for older adults and adults with "
                   "disabilities. Buddies provide social connection, not caregiving.",
        "location": "San Francisco; check the individual neighborhood or event",
        "published_price_cents": None,
        "price_note": "Fees, if any, depend on the selected program and are unverified here.",
        "unknowns": ["Specific event date, seats, access needs, and cost", "Program eligibility",
                     "Volunteer capacity and registration acceptance"],
        "next_steps": ["Choose an activity the resident wants from the official calendar.",
                       "Check that event's schedule, access needs, costs, and registration requirements.",
                       "Confirm participation and any travel support separately; leaving the time free is valid."],
    },
    {
        "id": "sf_das", "kind": "directory", "provider": "SF Disability and Aging Services",
        "name": "City support and referral directory", "needs": ["everyday_help", "community"],
        "url": "https://www.sfhsa.org/services/disability-aging",
        "summary": "An official entry point to community support and referrals. "
                   "Individual directory listings have not been checked for this catalog.",
        "location": "San Francisco",
        "published_price_cents": None,
        "price_note": "A referral source, not a priced service offer.",
        "unknowns": ["The appropriate individual provider", "Provider eligibility, fees, and capacity"],
        "next_steps": ["Identify the requested support through the official city service page.",
                       "Review the individual provider's terms and contact route.",
                       "Obtain provider acceptance before describing help as arranged."],
    },
]


def match_options(need="home_storage", budget_cents=None):
    """Match an explicit need; expose unresolved constraints rather than inventing fit."""
    if type(need) is not str or need not in NEEDS:
        raise ValueError("Choose one supported household need.")
    if budget_cents is not None and (type(budget_cents) is not int or budget_cents < 0):
        raise ValueError("Budget must be nonnegative integer cents.")
    options = []
    for source in _OPTIONS:
        if need not in source["needs"]:
            continue
        item = deepcopy(source)
        item.pop("needs")
        item.setdefault("source_urls", [item["url"]])
        item["checked_at"] = CHECKED_AT
        item["match_reason"] = f"Its published scope relates to: {NEEDS[need].lower()}."
        price = item["published_price_cents"]
        item["budget_status"] = (
            "not_supplied" if budget_cents is None else
            "listed_item_price_above_budget" if price is not None and price > budget_cents else
            "total_unknown"
        )
        item["coordination_status"] = "not_requested"
        options.append(item)
    return {
        "city": "San Francisco", "checked_at": CHECKED_AT,
        "source_mode": "curated_public_sources", "need": need, "budget_cents": budget_cents,
        "needs": [{"id": key, "label": label} for key, label in NEEDS.items()],
        "notice": "Public source snapshots checked September 8, 2026. These are candidates, not live "
                  "stock, quotes, partnerships, or confirmed matches. No provider has been contacted. "
                  "Selection, requests, acceptance, delivery, and completion require separate evidence.",
        "options": options,
    }
