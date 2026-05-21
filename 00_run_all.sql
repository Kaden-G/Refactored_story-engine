-- ============================================================
-- MAMS — Run All Scripts
-- Usage:  psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
-- Builds schema, loads SQL features, then seeds the Greywatch world.
-- ============================================================
\echo 'Building MAMS schema...'
\i 01_objective_layer.sql
\echo '  Objective Layer done.'
\i 02_agent_layer.sql
\echo '  Agent Layer done.'
\i 03_epistemic_layer.sql
\echo '  Epistemic Layer done.'
\echo 'Installing SQL features...'
\i 05_functions.sql
\echo '  Functions done (3).'
\i 06_procedures.sql
\echo '  Procedures done (3).'
\i 07_triggers.sql
\echo '  Triggers done (3).'
\echo 'Loading Greywatch seed data...'
\i 04_seed_data.sql
\echo 'MAMS build complete — 18 tables, 9 SQL features, Greywatch world.'
