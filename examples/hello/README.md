# hello

Two agents, alice and bob, on one broker. Alice sends a message to bob, bob's listener writes it to a sidecar file.

## Run

Start the broker in one terminal:

    docker compose -f ../../broker/docker-compose.yml up

In a second terminal, start bob's listener:

    cd examples/hello
    chatmesh listen --config bob.toml

In a third terminal, publish from alice:

    cd examples/hello
    chatmesh publish --config alice.toml --to bob --topic greet "hello bob"

The message id prints on stdout, and the envelope lands in `bob.jsonl` next to `bob.toml`.
