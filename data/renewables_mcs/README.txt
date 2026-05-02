Renewables deployment (MCS-style) — source workbooks
======================================================

Place the Ofgem MCS-style Excel files listed below in this directory. Names must
match exactly as registered in metadata/xlsx_registry.yaml (the loader also
accepts the same spelling with different letter case).

They are registered under data_dir: data/renewables_mcs.

Required filenames (all six for full mart_renewables_deployment coverage)
-------------------------------------------------------------------------

Each workbook maps to a slice of mart_renewables_deployment.grain:

  Total_installed_capacity_kW_by_technology_type.xlsx
      -> grain annual_gb (capacity_kw)

  Installations_by_technology_type.xlsx
      -> grain annual_gb (installations)

  Installations_by_technology_per_quarter_non_cumulative.xlsx
      -> grain quarterly_gb (installations)

  Capacity_kW_by_technology_per_quarter.xlsx
      -> grain quarterly_gb (capacity_kw)

  Regional_breakdown_of_share_of_installations_and_TIC.xlsx
      -> grain regional (share_pct, capacity_kw, installations where present)

  Total_installed_capacity_kW_by_installation_type.xlsx
      -> grain by_installation_type (capacity_kw by domestic vs non-domestic /
         commercial / industrial per registry column_dimension_map)

Any subset loads into raw_xlsx_renewables; missing files only skip those grains.

Technical notes
---------------

  • Registry entries use sheet index 0 (first worksheet) because published MCS
    exports often do not name the data sheet "Sheet1".

Then reload the pipeline (the `marts` command runs staging first, so you do not
need a separate `staging` step):

  python -m pipeline.orchestrate xlsx
  python -m pipeline.orchestrate marts

Or in one step:

  python -m pipeline.orchestrate full_refresh

The loader skips missing files with a warning; mart_renewables_deployment stays
empty until at least one workbook produces rows in raw_xlsx_renewables.
