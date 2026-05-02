Warm Home Discount (WHD) — source workbooks
============================================

Place the Ofgem WHD Excel files listed below in this directory. Names must
match exactly as registered in metadata/xlsx_registry.yaml (the loader also
accepts the same spelling with different letter case).

They are registered under data_dir: data/whd.

Required filenames
------------------

  WHD_distribution_of_expenditure_by_year_England_and_Wales.xlsx
  WHD_distribution_of_expenditure_by_year_Scotland.xlsx
  WHD_scheme_value_since_2002.xlsx
  WHD_supplier_obligation_methods_since_2002.xlsx
  WHD_funds_redistributed_to_suppliers_since_2002.xlsx

Any subset loads into raw_xlsx_whd; missing files skip those series until present.

Then reload the pipeline (the `marts` command runs staging first):

  python -m pipeline.orchestrate xlsx
  python -m pipeline.orchestrate marts

Or in one step:

  python -m pipeline.orchestrate full_refresh

The loader skips missing files with a warning; mart_warm_home_discount stays
sparse or empty until workbooks produce rows in raw_xlsx_whd.
