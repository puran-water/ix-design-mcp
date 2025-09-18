# Next Steps for Codex Agent

1. **Launch the MCP server with the mirrored configuration**
   - Run the agent from the project root so it picks up `.codex/config.toml`.
   - Verify the Python virtual environment at `/mnt/c/Users/hvksh/mcp-servers/venv312/Scripts/python.exe` is active and has the dependencies from `requirements.txt`.

2. **Smoke-test SAC multi-vessel handling**
   - Create a sample SAC request with `number_service > 1` and ensure breakthrough time and regeneration outputs scale with the total system flow.
   - Capture the JSON response from `simulate_sac_ix` and confirm the new `total_*` fields match the per-vessel values multiplied by the service count.

3. **Smoke-test WAC flows**
   - Run `configure_wac_ix` and `simulate_wac_system` for both `WAC_Na` and `WAC_H` cases.
   - Confirm hardness/alkalinity calculations reflect the corrected CaCO₃ conversions and that Na-form regeneration reports the 110%/120% stoichiometric dosing.

4. **Document expected outputs**
   - Record sample inputs/outputs in `results/` (or an alternative scratch directory) to serve as regression references for future runs.

5. **Assess downstream consumers**
   - If any tooling expects the old per-vessel-only fields, update or document the new `total_*` and `service_vessels` metadata so dashboards/tests remain in sync.
