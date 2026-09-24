# Existing agent runbook

This path assumes the work computer, Graph login, and the current agent session
remain alive. Pager transports commands; it does not launch or recover an agent.

## Setup

```powershell
$env:PAGER_CONTROL_ADDRESS = "your.name@example.com"
$env:PAGER_STATE_PATH = "$HOME\.pager\<workspace>.json"
```

Use one state file per workspace. A task id is single-use and should contain the
workspace, purpose, and UTC timestamp.

## Control loop

1. Send a page whose body says exactly what `OK` would approve:

   ```powershell
   python -m pager send --task-id <id> --title "<short title>" --body "<choices>"
   ```

2. Start the persistent listener:

   ```powershell
   python -m pager serve --heartbeat-seconds 3600
   ```

   Empty polls keep running. Exit 0 returns command JSON; restart `serve` after
   handling it. A non-zero exit stops new work and must be reported as an error.
   Heartbeats are notifications and do not open control tasks.

3. Dispatch the returned verb:

   - `DO`: treat `text` as a natural-language task in the named workspace. Never
     concatenate it into a shell command. Apply normal approval and safety rules.
   - `OK`: perform only the action stated in that page. It is not general consent.
   - `NO`: cancel that action and report the cancellation.
   - `STOP`: stop at the next safe checkpoint and report what remains. It cannot
     interrupt a command already running.

   `OK`, `NO`, and `STOP` must be the only token on the first non-empty line.
   `DO` requires text after it. An invalid reply leaves the page pending.

4. Send the result, then send a new standby page with a new task id. A valid
   reply closes the old task id; later replies to that thread are ignored.

## Failure boundary

Pager persists mailbox consumption, not task completion. If the agent crashes
after `serve` returns but before finishing the task, that command is not replayed.
Do not describe this mode as crash-recoverable or able to wake an exited agent.
Closing the terminal or rebooting the work computer stops `serve`.
