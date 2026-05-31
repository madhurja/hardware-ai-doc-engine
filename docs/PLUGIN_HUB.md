# Plugin Hub

The app now includes a plugin and internet-reference hub for hardware documentation work.

## Included Plugin Families

| Family | Purpose | Access |
| --- | --- | --- |
| Octopart / Nexar | Part search, datasheets, availability, alternates, and API-ready supply-chain automation. | Browser links now; API credentials later. |
| DigiKey | Product information, stock, price, and datasheet research. | Browser links now; developer API credentials later. |
| Mouser | Distributor search and datasheet evidence gathering. | Browser links. |
| LCSC | Manufacturing-oriented low-cost part lookup. | Browser links. |
| KiCad CLI | Future local ERC, DRC, BOM, netlist, Gerber, and plot/export automation. | Local tool detection and official docs. |
| Compliance Reference Pack | FCC, EU harmonised standards, RoHS, wireless, and high-speed validation research. | Browser links. |
| OpenAI Assisted Drafting | Optional cloud-assisted writing after local evidence extraction. | API key only when enabled by the user. |
| PWA App Mode | Easier Windows and Android access through browser installation. | Built in. |
| Internal Quality Audit | Blocker/major/minor flaw scoring and release status. | Built in. |

## How It Works

The backend builds a plugin catalog from the current schematic, PCB, and firmware analysis. The browser app shows:

- Plugin cards grouped by category
- Setup notes and current status
- One-click supplier and datasheet links for detected key parts
- Standards and CAD reference links
- API-ready plugins that can be upgraded later with credentials

## Safety Model

Internet links open in the user's browser. The app does not upload schematics, BOMs, firmware, or generated PDFs to those services automatically. API automation is prepared but intentionally requires explicit credentials before use.
