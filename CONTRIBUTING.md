# Contributing

Issues and pull requests are welcome. This is a small project with one
maintainer, so the bar is: it works, it is tested, and it does not make the
thing harder to explain.

## Getting set up

    git clone https://github.com/g-postigo/chatmesh.git
    cd chatmesh
    pip install -e ".[dev]"
    pytest

That runs everything except the integration tests, which skip themselves unless
a broker is reachable. To run those too:

    docker compose -f broker/docker-compose.yml up -d
    pytest

Before you open a pull request:

    ruff check .
    ruff format .
    pytest

CI runs the same three on Linux, macOS and Windows against Python 3.11 through
3.14. There is no other gate.

## Good first contributions

**A new driver.** This is the obvious one. A driver turns a message into an
answer, and the interface is one method:

    class MyDriver(Driver):
        async def handle(self, env: Envelope) -> str | Reply | None: ...

[OpenAIDriver](src/chatmesh/drivers/openai.py) is about 90 lines and is the one
to copy. Reuse `Room` and `parse_reply` from `drivers/_chat.py` so your driver
gets the same room semantics as the rest: the channel header, the roster, and
the `@name:` / `@all:` / `@skip` prefixes. Anthropic's own API, Gemini, Bedrock
and local runners that do not speak the OpenAI shape are all open.

**Broker deployment notes.** [docs/broker-production.md](docs/broker-production.md)
covers one way to run this. If you run NATS somewhere else, that is worth
writing down.

**Bug reports with a reproduction.** Even a rough one. Several of the fixes in
the changelog came from running the thing and watching it misbehave, not from
reading the code.

## What tends to get pushed back

- A new runtime dependency for something the standard library does. `nats-py` is
  the only required one and it should stay that way.
- An abstraction with a single implementation behind it.
- Speculative configuration. If nothing today needs the value to change, it is
  not a setting yet.

None of that is a rejection, it is just a conversation. Open an issue first if
you are unsure whether something fits.

## Tests

Every behaviour change needs a test that fails without it. The integration
tests under `tests/integration/` need a real broker and skip cleanly when there
is not one, which is the right home for anything involving delivery, routing or
timing.

If a test could pass for the wrong reason, add the control case.
`tests/integration/test_durable.py` has one: the same scenario with durability
off, asserting the messages are lost. That pair caught a real mistake, where the
durable test was green only because a stray relay process happened to be running
on the development machine.

## Style

Line length 100, `ruff format` decides the rest. Prose in the docs, the README
and commit messages: plain English, short sentences, no em-dashes, no decorative
headers. Write like a person explaining something to a colleague.

Commit messages say what changed and why. A subject line and a few lines of
reasoning beats a long list.

## License

MIT. By contributing you agree your work ships under it.
