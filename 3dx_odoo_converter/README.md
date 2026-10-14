# 3DEXPERIENCE to Odoo converter

> **Handover status (October 2026):** The file-based converter and automated tests are working. It has not yet been validated against the team's Odoo database with a real Released installation. Use a test database and review the generated audit report before wider use.

This command-line tool converts a 3DEXPERIENCE **installation product-structure** CSV into separate Odoo product and Bill of Materials (BoM) CSV and XLSX import files. It also creates an audit report so quantity assumptions, release-state holds, manual procurement entries, and invalid rows are visible before anything is imported. The CSV workflow is the first connector step; it does not connect to either service's API.

For a quick repository overview, see the [root README](../README.md). This guide contains the full input contract, converter behaviour, codebase map, and Odoo import procedure.

## What it creates

Running the converter creates CSV and Excel versions of each Odoo import, plus an Excel audit report:

- odoo_products_import.xlsx — import into Odoo Products first.
- odoo_bom_import.xlsx — import into Odoo Bills of Materials second.
- odoo_products_import.csv and odoo_bom_import.csv — the same import rows in CSV form. Use either CSV or XLSX for each model, not both.
- conversion_report.xlsx — review this before importing; it contains summary counts, warnings, rejected rows, and source-to-Odoo mappings.

The product and BoM imports are deliberately separate files because Odoo imports those models separately. A BoM's finished product uses its stable Odoo External ID. Component lines use unique Internal References because Odoo stores the imported External ID on `product.template`, while BoM components must resolve to `product.product` variants. Product names are never used as relationship keys.

3DX products are exported with **Can be Purchased = False** because this workflow treats them as manufactured parts. Ready manual procurement items are exported with **Can be Purchased = True**.

## Requirements

- Python 3.10 or newer
- pip
- A 3DEXPERIENCE CSV containing: Level, Name, Title, Revision, Enterprise Item Number, and Maturity State

Install the Python dependencies:

    cd 3dx_odoo_converter
    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt

On Windows PowerShell, activate the virtual environment with:

    .venv\Scripts\Activate.ps1

## Convert a CSV

From the 3dx_odoo_converter directory:

    python convert_3dx_to_odoo.py "../ASM-DOORS INSTALLATION.csv" --project-id PROJECT-123 --output-dir ./odoo_output

The supplied sample has one Level 0 assembly and four Level 1 components. It is entirely **In Work**, so this command writes only `conversion_report.xlsx` and exits with an error. That is expected: no Odoo import files are produced until the entire installation branch is `Released`. Use a real released installation export for a successful import run. Export **installations / physical product structures**, not drawing records.

For a real Released installation, point the command at that export. Keep each run's files together in one output directory:

    python convert_3dx_to_odoo.py "/path/to/RELEASED INSTALLATION.csv" \
      --project-id PROJECT-123 --output-dir ./odoo_output

If the source contains approved quantities, add `--quantity-column` with the exact CSV header. Do not change an item's 3DEXPERIENCE maturity state solely to make the converter accept it.

Successful output looks like:

    Conversion completed.

    Product rows exported: 5
    BoMs created: 1
    BoM component lines: 4
    Existing products matched: 0
    Existing assemblies matched: 0
    Manual procurement rows exported: 0
    Rejected rows: 0

    Files:
    - odoo_products_import.xlsx
    - odoo_bom_import.xlsx
    - odoo_products_import.csv
    - odoo_bom_import.csv
    - conversion_report.xlsx

## Options

This example shows the available settings; use only the options relevant to your run:

    python convert_3dx_to_odoo.py input.csv \
      --output-dir ./output \
      --project-id PROJECT-123 \
      --procurement-csv ./manual_procurement.csv \
      --default-quantity 1 \
      --quantity-column Quantity \
      --default-uom Units \
      --product-type Goods \
      --bom-type "Manufacture this product" \
      --existing-products ./odoo_existing_products.xlsx \
      --field-mapping ./odoo_field_mapping.json

- Release gating is always on. An installation is held if its root or any descendant is not `Released`; the converter never exports a partial installation BoM. If no installation is fully released, it creates only the audit report. `--released-only` is accepted for old scripts but is now redundant.
- --project-id labels the audit report and each BoM Reference. It must match the Project ID in a manual procurement CSV. The project ID is a traceability key, not an Odoo Project relationship; mapping to a custom Odoo project field requires that field's actual name in the target database.
- --procurement-csv reads manually entered purchased parts absent from 3DX. See below.
- --quantity-column names a future CSV quantity column. Values must be positive numbers. Without it, each component occurrence uses --default-quantity and the report warns that the quantity was assumed.
- --product-type and --bom-type accommodate differing Odoo version labels.
- --default-uom is written to both Odoo UoM fields.
- --existing-products reconciles converted products with an Odoo product export. It reuses the
  existing External IDs so product rows update the stubs and BoMs attach to those records. It
  matches Internal Reference first, then a unique exact Name. If any assembly is missing or
  ambiguous, conversion stops rather than creating a duplicate assembly.

Repeated immediate component lines are combined. For example, three occurrences of the same component with the default quantity of 1 become one BoM component line with quantity 3.

## How the conversion works

### Source data and hierarchy

The source must be a UTF-8 CSV export of an **installation / physical product structure**, with these exact column names:

| Required column | How the converter uses it |
| --- | --- |
| `Level` | `0` starts an installation; each higher level belongs to its nearest parent at the preceding level. A child without that parent is rejected. |
| `Name` | 3DEXPERIENCE identifier used when an Enterprise Item Number is missing. |
| `Title` | Product name shown in Odoo. A trailing `(Default_speedpak)` suffix is removed. |
| `Revision` | Included in the generated BoM External ID and its reference. |
| `Enterprise Item Number` | Preferred product identity and Internal Reference. If blank, `Name` must be present. |
| `Maturity State` | Must be exactly `Released` for an installation branch to enter an Odoo import. |

An optional `Type` column is checked for drawing records. If it identifies a drawing, conversion stops: export the installation structure instead. An optional quantity column is read only when its name is passed through `--quantity-column`. Otherwise every component occurrence uses `--default-quantity` (default `1`) and the report warns that the quantity was assumed. Confirm quantities with engineering before importing.

The converter can read multiple Level 0 installations in one CSV. A parent with children becomes a BoM; nested parents can therefore have their own BoMs. A product that appears more than once is written once, while repeated occurrences under the same immediate parent have their quantities summed.

### Processing and safety rules

1. **Parse:** read the CSV, normalise blank values, and attach each row to its immediate parent.
2. **Gate and validate:** hold an entire installation when its root or any descendant is not `Released`. Check required data, positive quantities, identities, generated ID collisions, self-references, and malformed rows. Other fully Released installations in the same file can still be exported.
3. **Transform:** create unique Odoo Products and one BoM per included parent with children. 3DX products are non-purchasable; their names come from `Title`. The finished product is linked by Product External ID, and a component is linked by its unique Internal Reference.
4. **Add manual procurement (optional):** include `Ready` purchased parts only when their parent is in a fully Released installation. Draft and held rows remain in the audit report.
5. **Reconcile existing Odoo products (optional):** reuse External IDs from a supplied Odoo export. Match by Internal Reference first, then by unique Name. Missing or ambiguous assembly matches stop the run.
6. **Write outputs:** always write the audit report once inputs have been parsed. When validation or reconciliation fails, return a non-zero exit code and remove stale Product and BoM import files from the chosen output directory.

Product IDs are derived from the engineering identifier; BoM IDs include the parent identifier and revision; BoM line IDs include the component reference. Keep those identifiers stable between runs. Changing an identifier or revision can make Odoo treat a row as a different record. The output files do **not** create purchase orders, vendor records, Odoo Project links, or tasks.

### Output files

| File | Purpose |
| --- | --- |
| `odoo_products_import.xlsx` / `.csv` | Product records, including manufactured 3DX products and eligible purchased items. Import first. |
| `odoo_bom_import.xlsx` / `.csv` | Parent BoMs and component lines. Import after Products. |
| `conversion_report.xlsx` | Review-only audit workbook. Never import this into Odoo. |

The Excel and CSV versions of an import contain the same rows. Choose one format for each Odoo model. The audit report has **Summary**, **Warnings**, **Rejected Rows**, **Source Mapping**, and **Procurement** sheets. A warning alone does not stop export; a rejected row or validation error does.

## Codebase guide for TSS

The entry point is `convert_3dx_to_odoo.py`. It reads command-line options and runs the stages below in order. The `converter/` package contains the business rules, while `tests/` exercises each stage and complete command-line runs.

| File | Responsibility |
| --- | --- |
| `converter/models.py` | Typed data structures for source rows, Odoo products, BoMs, warnings, and rejected rows. |
| `converter/parser.py` | Required CSV columns, row cleaning, hierarchy, and parent links. |
| `converter/validator.py` | Release gating, quantity interpretation, identity checks, and validation errors. |
| `converter/transformer.py` | Product and BoM construction, stable identifiers, duplicate line consolidation, and output rows. |
| `converter/procurement.py` | Manual purchased-part CSV, Ready/Draft decisions, and purchased BoM lines. |
| `converter/reconciler.py` | Matching an Odoo Product export to existing records and reusing their External IDs. |
| `converter/odoo_writer.py` | Field-mapping validation plus CSV/XLSX import-file writing. |
| `converter/report_writer.py` | Audit workbook and its five review sheets. |
| `odoo_field_mapping.json` | Odoo import column labels; change this for database-specific headers. |
| `tests/` | Parser, validation, transformation, reconciliation, procurement, and end-to-end tests. |

For a change to **source interpretation**, start in `parser.py` or `validator.py`; for an Odoo value or relationship, inspect `transformer.py` and `odoo_writer.py`; for manually purchased parts, use `procurement.py`. Add a focused test for the rule changed, then run the whole suite. If adding a new Odoo column, update the model, row construction, writer keys, `odoo_field_mapping.json`, documentation, and an end-to-end test together.

## Manual procurement items

Make a UTF-8 CSV with this header:

    Project ID,Parent Reference,Internal Reference,Name,Quantity,Unit of Measure,Status
    PROJECT-123,ASM-001,BUY-001,M8 fastener,12,Units,Ready
    PROJECT-123,,BUY-002,Future bracket,1,Units,Draft

`Parent Reference` is the parent 3DX product's **Internal Reference** (Enterprise Item Number, or `3DX-` followed by Name when that number is missing). `Ready` means the item is approved for procurement; `Draft` stays in the audit register. A Ready item enters the Odoo Products and BoM imports only when its parent is in a fully Released installation. A blank or held parent also stays in the register. Repeated Ready rows for the same item and parent add their quantities. The manual item's Internal Reference must be unique and absent from 3DX. Its product External ID contains the project ID and reference, so keep those identifiers stable across repeat imports.

Run:

    python convert_3dx_to_odoo.py installation.csv --project-id PROJECT-123 \
      --procurement-csv manual_procurement.csv --output-dir ./odoo_output

Review the **Procurement** sheet in `conversion_report.xlsx`: it shows every manual row as Exported or Held with a reason. The converter creates purchasable Products and BoM lines. Actual purchase orders, vendor selection, receipt status, and project task tracking remain Odoo workflow steps; this CSV does not create those records.

Every BoM component line receives a stable External ID. This is intended to let a repeat import
update lines rather than append duplicates; TSS should verify that behaviour in the target Odoo
database. BoMs imported with an older converter version may lack those line identifiers. Check
them in staging and plan a controlled one-time replacement if needed before repeat imports.

The 3DEXPERIENCE representation suffix `(Default_speedpak)` is removed from product names. It is technical representation metadata rather than part of the user-facing product title.

## Configure Odoo headers

`odoo_field_mapping.json` is the source for both Excel and CSV import headers. Edit its values, not the Python code, if the target Odoo database exports different field labels.

Before a staging or production import, export one Product and one BoM from the target Odoo database. Compare their import headers with `odoo_field_mapping.json` and update the JSON values to match exactly. Different Odoo versions, installed modules, and custom fields can alter these labels.

## Odoo import sequence

Import into a test or staging database before using these files in production. The user performing
the import needs permission to create or update Products and Bills of Materials, and the
Manufacturing app must be installed.

Always import `odoo_products_import.xlsx` (or `.csv`) first and `odoo_bom_import.xlsx` (or `.csv`) second. Do not import
`conversion_report.xlsx`; it is an audit workbook for review only. The BoM file refers to parent
Product External IDs and component Internal References created or updated by the product import.

### Before importing

1. Open `conversion_report.xlsx` and review the **Summary**, **Warnings**, and **Rejected Rows**
   sheets. Investigate every warning that matters to the intended import. Do not continue if the
   report contains rejected rows that should have been imported.
2. Confirm that `odoo_products_import.xlsx` and `odoo_bom_import.xlsx` came from the same converter
   run. Do not mix product and BoM files from different runs.
3. Check whether the target Odoo database already contains any of the assemblies or components.
   If it does, follow **Importing when products already exist** below before proceeding. Do not
   create a second copy of an existing assembly simply to complete the import.
4. For a production import, make a backup or confirm that a current Odoo backup is available.

### Import 1: Products

1. In Odoo, open **Inventory > Products > Products**. The Product list can also be reached through
   another installed app, but start from the full Products list rather than a product form.
2. Click the **Actions** icon in the list view and select **Import records**.
3. Click **Upload Data File** and select `odoo_products_import.xlsx`.
4. In the import preview, verify that each **File Column** is mapped to the following Odoo field:

   | File column | Odoo field |
   | --- | --- |
   | `External ID` | External ID |
   | `Name` | Name |
   | `Internal Reference` | Internal Reference |
   | `Product Type` | Product Type |
   | `Can be Sold` | Can be Sold |
   | `Can be Purchased` | Can be Purchased |
   | `Unit of Measure` | Unit of Measure |
   | `Purchase Unit of Measure` | Purchase Unit of Measure |

   Odoo normally maps these columns automatically. If a column is not mapped, select the matching
   field manually from its drop-down. Map `External ID` to **External ID**, not **Database ID**.
5. Click **Test**. Do not click **Import** while Odoo reports an error. Correct the source data,
   field mapping, configured command option, or `odoo_field_mapping.json`, rerun the converter when
   necessary, and test the new workbook again.
6. When the test succeeds, click **Import** and wait for Odoo's completion message. Do not refresh
   or close the page while the import is running.
7. Return to the Products list and verify the result:
   - Search for one imported product by its exact **Internal Reference**.
   - Open the product and confirm its Name, Product Type, Unit of Measure, purchase setting, and
     sales setting.
   - Confirm that the expected number of new products was created and that existing matched
     products were updated rather than duplicated.

The product import also creates each new product's default product variant. The variant retains the
unique Internal Reference used to resolve component rows during the BoM import.

### Import 2: Bills of Materials

Start this import only after the product import and its verification have completed successfully.

1. In Odoo, open **Manufacturing > Products > Bills of Materials**.
2. Click the **Actions** icon in the list view and select **Import records**.
3. Click **Upload Data File** and select `odoo_bom_import.xlsx`.
4. Verify every column mapping in the import preview. Expand the related BoM-line fields when
   necessary and map the columns as follows:

   | File column | Odoo field |
   | --- | --- |
   | `External ID` | External ID |
   | `Product/External ID` | Product / External ID |
   | `Quantity` | Quantity |
   | `BoM Type` | BoM Type |
   | `BoM Lines/External ID` | BoM Lines / External ID |
   | `BoM Lines/Component` | BoM Lines / Component |
   | `BoM Lines/Quantity` | BoM Lines / Quantity |
   | `BoM Lines/Unit` | BoM Lines / Unit |
   | `Reference` | Reference |

   `BoM Lines/External ID` is required even if Odoo does not map it automatically. These stable
   line identifiers allow a later import of the same converted BoM to update component lines
   instead of appending another copy of every line.
5. Click **Test** and review the complete result. Common failures and their likely causes are:
   - **Product not found** for `Product/External ID`: the product workbook was not imported first,
     the product import failed, or the External ID was changed.
   - **Component not found**: the referenced product variant does not exist, or its Internal
     Reference no longer matches the product workbook.
   - **Multiple matches**: more than one Odoo product has the same Internal Reference. Correct the
     duplicate records before importing the BoM.
   - **Unknown unit of measure**: the value passed with `--default-uom` does not exist in this Odoo
     database or uses a different label.
   - **Invalid Product Type or BoM Type**: the target Odoo version uses a different selection label.
     Export a sample record from that database and pass the correct `--product-type` or
     `--bom-type` value when rerunning the converter.
   - **Unmapped column**: select the correct field manually. For recurring imports, update
     `odoo_field_mapping.json` to use the exact header exported by the target database.
6. When the test succeeds, click **Import** and wait for the completion message.
7. Return to **Manufacturing > Products > Bills of Materials**, open each imported BoM, and verify:
   - The finished Product is correct.
   - The BoM Type is correct.
   - The BoM Quantity and Unit of Measure are correct.
   - Every expected component is present once with the correct quantity and unit.
   - The Reference contains the expected assembly name and revision.

### Importing when products already exist

If assembly stubs or matching products already exist in Odoo, reconcile them before importing:

1. Open the Odoo Products list and select the relevant existing products.
2. Use **Actions > Export**.
3. Select **I want to update data (import-compatible export)**.
4. Export `External ID`, `Name`, and `Internal Reference` as CSV or XLSX.
5. Rerun the converter with `--existing-products` pointing to that export, for example:

       python convert_3dx_to_odoo.py input.csv \
         --existing-products ./odoo_existing_products.xlsx \
         --output-dir ./odoo_output

6. Review the new conversion report. Confirm the **Existing products matched** and **Existing
   assemblies matched** counts before importing the newly generated product and BoM workbooks.

The converter carries the existing Odoo External IDs into both workbooks. It matches Internal
Reference first and then a unique exact Name. If an assembly is missing or ambiguous, conversion
stops instead of creating a likely duplicate.

### Repeat imports and Odoo Online display

Odoo uses an imported External ID to update an existing record when the same file is imported
again. The converter also gives each BoM component line a stable External ID. Keep these columns in
the workbooks and preserve their mappings on every import.

Odoo Online normally displays a product's Internal Reference in brackets before its name, for
example `[SR8-DOR-0008] ASM-DOOR HINGE V5-LH`. This is expected Odoo behaviour. Do not clear the
Internal Reference merely to remove the bracketed text; it is the reliable component key used by
this import workflow. Odoo Online does not support installing the included custom display add-on.

For general details about the import screen, testing, External IDs, and repeat imports, see the
[Odoo 18 import documentation](https://www.odoo.com/documentation/18.0/applications/essentials/export_import_data.html).

## Validation and failures

The converter checks required columns, hierarchy parents, titles, product identifiers, External IDs, internal references, self-references, quantities, and duplicate component lines.

The conversion is atomic on validation failure: it returns a non-zero exit code and removes any stale Odoo import files in the selected output directory. It still writes conversion_report.xlsx so the source can be fixed. Warnings alone do not prevent conversion.

conversion_report.xlsx contains:

- Summary — source and output counts plus a timestamp.
- Warnings — assumed quantities, fallback engineering references, non-released items, and other non-blocking conditions.
- Rejected Rows — original source rows and the reason they cannot be imported.
- Source Mapping — how source values become Odoo fields.
- Procurement — manual purchasing entries and whether each entered the Odoo imports.

## Run the tests

From the repository root:

    cd 3dx_odoo_converter
    python -m pytest

The suite covers the parser, release and quantity validation, transformation, existing-product reconciliation, manual procurement, and command-line output. The end-to-end tests make a **temporary Released copy** of the supplied example to verify 5 products, 1 BoM, and 4 BoM lines. A separate test confirms the original **In Work** example produces only the audit report. These are offline tests; they do not test the team's live or staging Odoo database.

## TSS takeover checklist

1. **Use this branch's converter as the starting point.** Read this guide, install the requirements, and run the tests. Keep the sample's real `In Work` state unchanged; use a genuinely Released installation export for an import trial.
2. **Agree on expected engineering data.** Have an engineer check the assembly, component list, quantities, units, and revisions. The example CSV has no authoritative quantity column, and assumed quantities must be reviewed rather than accepted by default.
3. **Match the target Odoo database.** In a test database with Manufacturing enabled, export a Product and a BoM, confirm the field mapping and accepted Product/BoM types and units, then run the converter into a fresh output directory. If products already exist, include an import-compatible Odoo Product export through `--existing-products`.
4. **Trial the import in order.** Read every sheet of `conversion_report.xlsx`, test/import Products, then test/import BoMs. Compare the resulting Odoo records with the engineering baseline. Test a Ready and a held procurement item if the team intends to use that input.
5. **Test a repeat import.** Rerun conversion with the same stable identifiers and the current Odoo Product export. Confirm that products and BoM lines update without duplicates. Review any older BoMs that predate stable line IDs.
6. **Record the result and release decision.** Save the approved source format, command options, field mapping, audit report, Odoo import results, and any fixes. Nominate an owner, then review and merge this feature branch into `main` when the staging workflow is accepted.

The remaining deployment date depends on the staging result. The converter is a local file-generation tool, so “deployment” for this version means establishing an owned run-and-import process, not installing an API service.
