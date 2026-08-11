# Setup prompt for AI assistants

Copy everything below the horizontal line into any AI assistant (ChatGPT, Claude, Kimi, Cursor, Copilot Chat). It will walk you through the setup and confirm that everything works.

If you already know how to read a README, skip this file and open `README.md`.

---

You are helping me set up `chatmesh`, a Python library for connecting AI agents over NATS. I just cloned the repository. Please do the setup for me, verify each step, and tell me when it works.

Rules for you:

- Run one command at a time. After each one, tell me the output and whether it succeeded.
- If a step fails, stop, tell me the exact error, and propose the fix.
- Do not modify any file in this repository unless I approve.
- Use the platform I am on. If I am on Windows, use PowerShell or bash-for-Windows conventions. On macOS or Linux, plain bash.
- The whole thing should finish in under 10 minutes on a normal machine.

Three identities exist in the demo: `alice` and `bob` are AI agents, `user` is me (the human). The GUI and the manual `publish` command run as `user`. The AI drivers run as `alice` and `bob`.

Steps to perform, in order:

**Step 1. Verify Python 3.11 or newer.**

    python --version

If below 3.11, tell me and stop.

**Step 2. Verify Docker is installed and running.**

    docker ps

If Docker is not running, tell me to start Docker Desktop and wait.

**Step 3. Verify at least one AI CLI is on PATH.**

    where claude
    where kimi

At least one of the two must exist. If neither, tell me to install one:

- Kimi Code: https://platform.moonshot.ai/docs/getting-started/quickstart
- Claude Code: https://docs.anthropic.com/en/docs/claude-code

Remember which one is available. Use that one for the demo below.

**Step 4. Install the library in editable mode.**

    pip install -e ".[dev]"

Confirm it succeeds without errors.

**Step 5. Run the unit tests.**

    python -m pytest

Expect around 51 passed and 1 skipped. If anything fails, stop and tell me.

**Step 6. Bootstrap the demo.**

    chatmesh bootstrap

This creates a `mesh/` directory with three config files (`alice.toml`, `bob.toml`, `user.toml`), starts the local NATS broker in Docker, and prints the next commands. Tell me the output.

**Step 7. Start the relay.**

Open a new terminal and run:

    chatmesh relay --config mesh/user.toml

Leave it running. Tell me when you see it stay alive without errors.

**Step 8. Start the GUI.**

Open a new terminal and run:

    chatmesh gui --config mesh/user.toml

Then open http://127.0.0.1:8765 in a browser. The GUI represents me, the human. Anything I type there is sent as `user`.

**Step 9. Start one or both AI drivers.**

Open a new terminal per driver. Use whichever CLI you have installed:

    chatmesh drive --config mesh/alice.toml --driver claude
    chatmesh drive --config mesh/bob.toml   --driver kimi

Leave them running. First run may take up to 15 seconds while the CLI initializes.

**Step 10. Send a message from the user to bob.**

From the GUI: click the `bob` channel in the sidebar (it appears after bob's driver sends its first heartbeat, or you can type in the compose bar with the DM open). Type "reply with just: ok" and send.

Or from another terminal:

    chatmesh publish --config mesh/user.toml --to bob --topic hello "reply with just: ok"

**Step 11. Verify the reply arrived.**

In the GUI you should see bob's reply appear in the feed within about 30 seconds. It will be a short message like "ok".

**Step 12. Report.**

If step 11 succeeded, tell me:

    Setup complete. The demo works. You can now:
    - Chat with either AI from the GUI
    - Ask alice and bob to talk to each other by sending a kickoff
      to one of them saying "please have a short chat with <the other>"
    - Read docs/getting-started.md for the full CLI reference
    - Stop the demo by pressing Ctrl-C in each terminal, then
      docker compose -f broker/docker-compose.yml down

If step 11 did not produce a reply, check:

- Is the driver terminal still alive? Any error in it?
- Is the relay terminal still alive? Any error in it?
- Did the AI CLI (`claude` or `kimi`) print an authentication error? If yes, tell me to log in to that CLI (`claude` runs an interactive login; `kimi` has its own login command).

Report what you find and propose a fix.

End of prompt.
