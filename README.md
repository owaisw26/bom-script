# 3DEXPERIENCE to Odoo BoM converter

This repository contains a Python command-line tool that turns a 3DEXPERIENCE **installation / physical product structure** CSV into Product and Bill of Materials (BoM) import files for Odoo. It also writes an audit workbook so an engineer can review release holds, quantity assumptions, rejected rows, and manual procurement items before importing anything.

**Current scope:** file-based conversion and manual Odoo import. The tool does not connect to either service's API, create purchase orders, or deploy itself into Odoo. The automated suite passes, but the team's Odoo database still needs a controlled import trial before routine use.

**Branch for TSS:** the current implementation is on [agent/fix-odoo-bom-component-mapping](https://github.com/owaisw26/bom-script/tree/agent/fix-odoo-bom-component-mapping). Select that branch after forking; `main` is still at the original converter version.

## Start here

| Need | Where to go |
| --- | --- |
| Set up Python and run a conversion | [Converter setup and usage](3dx_odoo_converter/README.md#requirements) |
| Understand the code and data flow | [Codebase guide](3dx_odoo_converter/README.md#codebase-guide-for-tss) |
| Review every conversion rule | [Functionality](3dx_odoo_converter/README.md#how-the-conversion-works) |
| Import the files into Odoo | [Odoo import sequence](3dx_odoo_converter/README.md#odoo-import-sequence) |
| See what TSS should validate next | [TSS takeover checklist](3dx_odoo_converter/README.md#tss-takeover-checklist) |

## Repository layout

| Path | Purpose |
| --- | --- |
| [3dx_odoo_converter/](3dx_odoo_converter/) | Converter code, configuration, tests, and detailed operating guide. |
| [ASM-DOORS INSTALLATION.csv](ASM-DOORS%20INSTALLATION.csv) | Five-row example export. Every row is **In Work**, so it should produce only an audit report. |
| [odoo_addons/bom_clean_display/](odoo_addons/bom_clean_display/) | Optional Odoo 18 display add-on for deployments that permit custom modules. |

## Quick check

From the repository root, create a Python environment, install dependencies, and run the tests:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r 3dx_odoo_converter/requirements.txt
    cd 3dx_odoo_converter
    python -m pytest

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in PowerShell. For a successful conversion, use a genuinely **Released** installation CSV; the included example is intentionally held by the release rule. See the [detailed README](3dx_odoo_converter/README.md) for the command, output files, and import steps.
