# Changelog

All notable changes to the SignalBridge Django SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-10-02

Brought in line with `nugsoft/signalbridge-laravel-sdk` and
`nugsoft/signalbridge-php-sdk`: the same channels, the same typed exceptions, and
the same segment maths as the gateway.

### Fixed

- **Sends could be delivered and billed twice.** The HTTP session retried `POST`
  on 500/502/503/504 and on connection and read errors. The gateway charges a
  message the moment it accepts one, so a proxy 502 or a read timeout after the
  gateway had already queued a message sent and charged it again — up to four
  times for a batch of 100. Only reads (GET/HEAD/OPTIONS) are retried now; see
  "Retries" in the README.
- **Segment counting disagreed with the gateway**, so `estimate_cost()` quoted
  prices that invoices did not match. Three causes, all now covered by tests in
  `tests/test_segments.py`: the GSM alphabet held the two-character sequences
  `\n` and `\r` instead of a real line feed and carriage return, so every
  multi-line message was billed as Unicode; the escape-table characters
  (`^{}\[]~|€`) were missing, so a message containing a `{placeholder}` was
  billed as Unicode too; and Unicode segments counted characters rather than
  UTF-16 code units, so emoji were under-counted.
- **`signalbridge_send_sms` crashed on every run.** It passed `sender_id=` to a
  `send_sms()` that had no such parameter. `send_sms()` and `send_batch()` now
  accept `sender_id`.
- **`signalbridge_transactions` crashed on every run.** It read
  `result['data']['data']` and `data['current_page']`; the gateway returns a
  paginated resource whose rows are under `data` and whose counters are under
  `meta`.
- The cached balance is now scoped per token, so two clients in one process can
  no longer read each other's balance.
- The default gateway URL points at production
  (`https://signal-bridge.nugsoftapps.net/api`). It previously pointed at a
  staging host spelled differently in each repository.
- `find_packages()` no longer ships the `tests` and `examples` directories as
  importable packages.
- Removed `default_app_config`, which has had no effect since Django 3.2 and was
  removed from Django in 4.1.
- `MANIFEST.in` no longer references a `migrations` directory that does not exist.
- Packaging metadata lives only in `pyproject.toml`; `setup.py` is removed. The
  two files disagreed, and `pyproject.toml` wins, so the published package was
  getting the short description and three classifiers rather than the full set
  declared in `setup.py`.
- The license is declared as the SPDX expression `MIT` with `license-files`
  (PEP 639) instead of a `license` table and a `License ::` classifier, both of
  which setuptools deprecates and stops supporting in February 2027. Builds are
  now warning-free and `twine check` passes.
- Dropped `wheel` and `setuptools_scm` from the build requirements: neither was
  used, the version is static. The build now needs `setuptools>=77`.
- The README told readers to `pip install signalbridge-django`, which is not the
  name of this package.
- A 404 now says that `SIGNALBRIDGE_URL` must include `/api`, rather than
  reporting a generic error.

### Added

- Channel accessors: `client.sms`, `client.whatsapp`, `client.mobile_money`,
  `client.ussd`. The flat methods are kept and proxy to them.
- Delivery status: `get_message_status()` and `get_messages()`, including batch
  follow-up by ids.
- Webhook management: `list_webhooks()`, `create_webhook()`, `get_webhook()`,
  `update_webhook()`, `delete_webhook()`, `regenerate_webhook_secret()`.
- `signalbridge.webhooks` for verifying inbound webhooks: constant-time
  comparison against `request.body`, with `verify_request()` for Django views.
- CSV exports: `export_messages()` and `export_transactions()`.
- `request_credit()` for asking administrators for a top-up.
- WhatsApp templates via `client.whatsapp.send_template()`.
- Exceptions matching the other SDKs: `UnauthorizedException` (401),
  `RateLimitedException` (429) and `InsufficientPermissionsException` (403),
  which carries `required_ability` when a token is missing one.
- `signalbridge.segments`, the single home for the segment maths.
- Client-side validation of recipients, message length and batch entries, so
  obvious mistakes fail before a request is made.
- A test suite (51 tests) with every request faked.
- `reset_client()` for dropping the cached singleton in tests.

### Changed

- **Token abilities are now enforced by the gateway.** A token scoped to, say,
  `sms:send` is refused elsewhere with a 403. Tokens created with `*` — the
  default — are unaffected. See "Token abilities" in the README.
- Reading a balance no longer creates one on the gateway: a currency with
  nothing stored reads as zero.
- Minimum Python is now 3.9 (3.8 is end-of-life).

## [1.0.0] - 2025-01-XX

### Added
- Initial release of SignalBridge Django SDK
- Single and batch SMS sending functionality
- Balance management and transaction history
- Segment calculation for GSM 7-bit and Unicode messages
- Cost estimation before sending
- Django management commands (send_sms, check_balance, transactions)
- Django AppConfig integration
- Native Django settings support
- Comprehensive exception handling with typed exceptions
- Example Django views for real-world use cases
- HTTP session pooling for performance
