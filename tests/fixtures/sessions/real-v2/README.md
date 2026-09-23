A real session, recorded on 20 September 2026 with the plugin loaded through
`claude --plugin-dir`, under RECORD_VERSION 2.

The agent wrote three files, ran `python3 -m unittest discover`, and then
edited `src/calc.py` — a file the suite covers — before reporting that "all
tests still pass". That is acceptance row A-1 as it happens in life rather
than in a fixture: the check sits at log position 4, the edit at position 5,
and only the log order says so, since the hook stamps a record when the call
returns.

`claim-ledger.toml` is the configuration that session ran under.
