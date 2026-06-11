// Generates the Python (pydantic) baml_client used by swe_af/baml_bridge.py.
// version MUST equal the installed baml-py (see pyproject.toml).
generator target {
    output_type "python/pydantic"
    output_dir "../"
    version "0.222.0"
    default_client_mode sync
}
