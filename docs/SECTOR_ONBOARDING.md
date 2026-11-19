# Business registration

Owners sign up with a username and password and select a sector. Each sector collects the owner's full names, national identity number, business location, monthly turnover band and named employees with monthly salary bands.

| Sector | Details |
|---|---|
| Transport | Taxi/cab/catch-a-ride choice, routes and exact fares, VIN, license plate, working days and hours |
| Services | Salon/mechanic/plumber/electrician/bricklayer choice, service price band, working days and hours |
| E-Commerce | Shein runner/Takealot/Other, purchase, selling and shipping price bands |
| Retail | Clothing/fruits/food/all/Other, purchase and selling price bands |
| Agriculture | Farming/livestock/Other, output selling price band, separate farmland count and total size/unit, repeatable livestock types and counts |

Employees can be added individually or omitted when none. Each row has full names and a salary band, with Add another employee and Continue controls. Livestock and routes also support repeated entries, up to 50 each. Other choices require a description. Overnight hours must be marked explicitly. Farming requires land and livestock activity requires animals.

Price and turnover bands are M100–499, M500–999, M1,000–9,999, M10,000–49,999, M50,000 and above. Salary bands are M500–999, M1,000–9,999, M10,000–19,999, M20,000 and above. Turnover and salaries are monthly; transaction prices are per route/item/service/output as labelled.

Profiles remain private to their authenticated owner, use CSRF-protected forms, and save atomically with initial business/chart creation. An optimistic version prevents stale tabs from overwriting newer edits. Registration does not create financial entries, inventory valuation or payroll. IDs are strings, preserving leading zeros, and are self-reported.

Version 2 details are stored in `SectorProfile.details`. Updating an older profile preserves its original details under `previous_registration_details`. No automatic backfill or financial changes are required. The new `0002_ussdregistration` migration adds independent USSD registration storage; production application requires approval under AGENTS.md.

See [USSD API, payload, authentication and deployment](USSD_REGISTRATION.md).
