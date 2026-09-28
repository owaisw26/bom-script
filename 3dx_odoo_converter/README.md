# 3DEXPERIENCE to Odoo converter
This has been written using the help of AI, let me know if any issues do arise during set-up cheers. 

This command-line tool converts a 3DEXPERIENCE product-structure CSV into separate Odoo product and Bill of Materials (BoM) XLSX import files. It also creates an audit report so quantity assumptions, release-state warnings, and invalid rows are visible before anything is imported.

## What it creates

Running the converter creates three real Excel workbooks in the output directory:

- odoo_products_import.xlsx — import into Odoo Products first.
- odoo_bom_import.xlsx — import into Odoo Bills of Materials second.
- conversion_report.xlsx — review this before importing; it contains summary counts, warnings, rejected rows, and source-to-Odoo mappings.

The product and BoM imports are deliberately separate files because Odoo imports those models separately. A BoM's finished product uses its stable Odoo External ID. Component lines use unique Internal References because Odoo stores the imported External ID on `product.template`, while BoM components must resolve to `product.product` variants. Product names are never used as relationship keys.

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

    python convert_3dx_to_odoo.py "../ASM-DOORS INSTALLATION.csv" --output-dir ./odoo_output

The supplied sample has one Level 0 assembly and four Level 1 components. It is entirely in the In Work maturity state, so the normal command succeeds with warnings. Do not use --released-only against that sample unless you expect a validation failure.

Successful output looks like:

    Conversion completed.

    Product rows exported: 5
    BoMs created: 1
    BoM component lines: 4
    Existing products matched: 0
    Existing assemblies matched: 0
    Warnings: 12
    Rejected rows: 0

    Files:
    - odoo_products_import.xlsx
    - odoo_bom_import.xlsx
    - conversion_report.xlsx

## Options

    python convert_3dx_to_odoo.py input.csv
      --output-dir ./output
      --released-only
      --default-quantity 1
      --quantity-column Quantity
      --default-uom Units
      --product-type Goods
      --bom-type "Manufacture this product"
      --existing-products ./odoo_existing_products.xlsx
      --field-mapping ./odoo_field_mapping.json

- --released-only accepts only Released data. A non-released Level 0 assembly stops the conversion. Non-released components are excluded and reported.
- --quantity-column names a future CSV quantity column. Values must be positive numbers. Without it, each component occurrence uses --default-quantity and the report warns that the quantity was assumed.
- --product-type and --bom-type accommodate differing Odoo version labels.
- --default-uom is written to both Odoo UoM fields.
- --existing-products reconciles converted products with an Odoo product export. It reuses the
  existing External IDs so product rows update the stubs and BoMs attach to those records. It
  matches Internal Reference first, then a unique exact Name. If any assembly is missing or
  ambiguous, conversion stops rather than creating a duplicate assembly.

Repeated immediate component lines are combined. For example, three occurrences of the same component with the default quantity of 1 become one BoM component line with quantity 3.

The 3DEXPERIENCE representation suffix `(Default_speedpak)` is removed from product names. It is technical representation metadata rather than part of the user-facing product title.

## Configure Odoo headers

odoo_field_mapping.json is the only source for the Excel import headers. Edit its values, not the Python code, if the target Odoo database exports different field labels.

Before a production import, export one Product and one BoM from the target Odoo database. Compare their import headers with odoo_field_mapping.json and update the JSON values to match exactly. Different Odoo versions, installed modules, and custom fields can alter these labels.

## Odoo import sequence

If assembly stubs already exist, first export them from Odoo with these columns: `External ID`,
`Name`, and `Internal Reference`. Select **I want to update data (import-compatible export)** and
export as CSV. Run the converter with `--existing-products` pointing to that export. The converter
carries the exported External IDs into both output workbooks.

1. Open Products in Odoo and import odoo_products_import.xlsx.
2. Confirm Odoo updates the matched assembly stubs and creates only genuinely new products. This also creates each new product's default variant with the same unique Internal Reference.
3. Open Bills of Materials and import odoo_bom_import.xlsx.
4. Review created BoMs and component quantities.

Do not import the BoM file first: it refers to the parent product External ID and component Internal References that must already exist in Odoo.

## Validation and failures

The converter checks required columns, hierarchy parents, titles, product identifiers, External IDs, internal references, self-references, quantities, and duplicate component lines.

The conversion is atomic: if a validation error occurs, it returns a non-zero exit code and does not write the two Odoo import workbooks. It still writes conversion_report.xlsx so the source can be fixed. Warnings alone do not prevent conversion.

conversion_report.xlsx contains:

- Summary — source and output counts plus a timestamp.
- Warnings — assumed quantities, fallback engineering references, non-released items, and other non-blocking conditions.
- Rejected Rows — original source rows and the reason they cannot be imported.
- Source Mapping — how source values become Odoo fields.

## Run the tests

    cd 3dx_odoo_converter
    python -m pytest

The end-to-end test runs the converter against the supplied CSV and verifies its expected 5 products, 1 BoM, and 4 BoM lines.
