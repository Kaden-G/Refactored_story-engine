-- ============================================================
-- MAMS — Run All Schema Scripts
-- Usage:  psql -d mams -v ON_ERROR_STOP=1 -f 00_run_all.sql
-- Runs the three DDL layers in dependency order.
-- ============================================================
\echo 'Building MAMS schema...'
\i 01_objective_layer.sql
\echo '  Objective Layer done.'
\i 02_agent_layer.sql
\echo '  Agent Layer done.'
\i 03_epistemic_layer.sql
\echo '  Epistemic Layer done.'
\echo 'MAMS schema build complete — 18 tables.'
