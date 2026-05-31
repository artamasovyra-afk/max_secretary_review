# MAX Sandbox Fixtures

These fixtures are mock and sanitized assumptions for future MAX sandbox work.

They are not real MAX payloads and must be updated after the real bot sandbox audit confirms the actual event shapes.

Rules for this directory:

- do not store real `user_id` values;
- do not store real `chat_id` values;
- do not store bot tokens or webhook secrets;
- use `mock-*` identifiers and `example.invalid` URLs only;
- keep callback/button payloads as assumptions until validated against the real MAX Bot API.
