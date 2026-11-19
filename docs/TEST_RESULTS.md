# Test results (build environment, 2026-11-18)

Commands:
```
cd backend && python -m pytest -q                       # backend unit + API tests
cd frontend && npx vitest run                           # clipboard TSV/HTML tests
python -m app.cli demo && python -m app.cli serve       # then, from repo root:
python -m pytest e2e -q                                 # Playwright browser tests (grid copy, drawer, all pages)
```

## Backend + browser
```
backend/tests/test_adapters.py::test_publisher_feed_keeps_original_url_date_and_image PASSED [  1%]
backend/tests/test_adapters.py::test_google_news_items_are_flagged_as_aggregator_and_attributed_to_outlet PASSED [  3%]
backend/tests/test_adapters.py::test_query_builder_includes_local_terms_and_exclusions PASSED [  5%]
backend/tests/test_api.py::test_core_endpoints PASSED                    [  7%]
backend/tests/test_api.py::test_hide_demo_data PASSED                    [  8%]
backend/tests/test_api.py::test_export_selected_rows_in_given_order PASSED [ 10%]
backend/tests/test_api.py::test_shortlist_survives_rank_change PASSED    [ 12%]
backend/tests/test_api.py::test_weights_change_recomputes_from_observations PASSED [ 14%]
backend/tests/test_canonical.py::test_same_sku_merges PASSED             [ 15%]
backend/tests/test_canonical.py::test_alias_spelling_merges_without_sku PASSED [ 17%]
backend/tests/test_canonical.py::test_conflicting_sku_never_merges PASSED [ 19%]
backend/tests/test_canonical.py::test_different_model_number_never_merges PASSED [ 21%]
backend/tests/test_canonical.py::test_model_level_vs_colorway_are_distinct PASSED [ 22%]
backend/tests/test_canonical.py::test_key_is_stable PASSED               [ 24%]
backend/tests/test_export.py::test_tsv_alignment_quotes_newlines_nulls PASSED [ 26%]
backend/tests/test_export.py::test_formula_injection_neutralised_but_image_formula_allowed PASSED [ 28%]
backend/tests/test_export.py::test_image_url_validation PASSED           [ 29%]
backend/tests/test_export.py::test_csv_and_xlsx_roundtrip PASSED         [ 31%]
backend/tests/test_extract.py::test_sneaker_with_colorway_and_sku PASSED [ 33%]
backend/tests/test_extract.py::test_adidas_and_new_balance_skus PASSED   [ 35%]
backend/tests/test_extract.py::test_electronics_model_and_claims PASSED  [ 36%]
backend/tests/test_extract.py::test_lego_set_number_kept_in_name PASSED  [ 38%]
backend/tests/test_extract.py::test_generic_brand_mentions_are_not_products PASSED [ 40%]
backend/tests/test_extract.py::test_uncertain_dates_are_never_turned_into_days PASSED [ 42%]
backend/tests/test_extract.py::test_rumor_vs_official PASSED             [ 43%]
backend/tests/test_links.py::test_article_beats_thin_shop_and_purchase_kept_separate PASSED [ 45%]
backend/tests/test_links.py::test_article_only_is_a_success_without_purchase_url PASSED [ 47%]
backend/tests/test_links.py::test_blocked_pages_fall_back_to_title_match_honestly PASSED [ 49%]
backend/tests/test_links.py::test_user_can_override_primary PASSED       [ 50%]
backend/tests/test_links.py::test_single_product_lookup_does_not_touch_others PASSED [ 52%]
backend/tests/test_pipeline.py::test_demo_scan_end_to_end_flags_fixtures PASSED [ 54%]
backend/tests/test_pipeline.py::test_overlapping_categories_do_not_duplicate_products PASSED [ 56%]
backend/tests/test_pipeline.py::test_scope_and_exclude_keywords PASSED   [ 57%]
backend/tests/test_pipeline.py::test_tracking_mode_never_creates_products PASSED [ 59%]
backend/tests/test_pipeline.py::test_rumor_to_confirmed_to_delay_history PASSED [ 61%]
backend/tests/test_pipeline.py::test_deleting_preset_keeps_products_and_history PASSED [ 63%]
backend/tests/test_pipeline.py::test_table_filter_does_not_start_scan PASSED [ 64%]
backend/tests/test_pipeline.py::test_custom_industry_category_and_multi_selection PASSED [ 66%]
backend/tests/test_queue.py::test_failed_source_is_reported_honestly_and_keeps_data PASSED [ 68%]
backend/tests/test_queue.py::test_dedup_key_prevents_duplicate_jobs PASSED [ 70%]
backend/tests/test_queue.py::test_manual_jobs_run_first_but_scheduled_not_starved PASSED [ 71%]
backend/tests/test_queue.py::test_restart_recovers_interrupted_job PASSED [ 73%]
backend/tests/test_queue.py::test_link_job_pause_resume_checkpoint PASSED [ 75%]
backend/tests/test_scheduler.py::test_p1_daily_slot_is_0700_vietnam_time_including_weekends PASSED [ 77%]
backend/tests/test_scheduler.py::test_p2_weekly_monday_0700 PASSED       [ 78%]
backend/tests/test_scheduler.py::test_p3_never_scheduled PASSED          [ 80%]
backend/tests/test_scheduler.py::test_tick_is_idempotent_and_catches_up_once PASSED [ 82%]
backend/tests/test_scheduler.py::test_new_preset_does_not_fire_for_past_slot PASSED [ 84%]
backend/tests/test_scheduler.py::test_manual_scan_does_not_modify_preset PASSED [ 85%]
backend/tests/test_scoring.py::test_missing_signals_are_excluded_not_zero PASSED [ 87%]
backend/tests/test_scoring.py::test_small_sample_growth_is_damped PASSED [ 89%]
backend/tests/test_scoring.py::test_single_mention_is_insufficient_data PASSED [ 91%]
backend/tests/test_scoring.py::test_syndicated_copies_do_not_count PASSED [ 92%]
backend/tests/test_scoring.py::test_growth_requires_observation_window PASSED [ 94%]
e2e/test_ui.py::test_every_page_renders_without_errors PASSED            [ 96%]
e2e/test_ui.py::test_copy_selected_rows_to_google_sheets_tsv PASSED      [ 98%]
e2e/test_ui.py::test_product_drawer_and_single_product_link_search PASSED [100%]
============================= 57 passed in 24.35s ==============================
```

## Frontend
```
 ✓ src/clipboard.test.ts (2 tests) 4ms
 Test Files  1 passed (1)
      Tests  2 passed (2)
```

## Live-source check in the build environment
`python -m app.cli scan --preset 1` → job **FAILED** (honestly): every outbound request was refused by the sandbox network proxy
(`403 Forbidden` on CONNECT). Sources were marked `ERROR`, `YOUTUBE_API_KEY` missing → `NOT_CONFIGURED`; no data was created
or overwritten. Live fetching must be verified on your own machine with **Source Manager → Test**.
