# Consent

## What VoiceForge requires

Every `POST /v1/voices` request must include `consent=true` (multipart form).
The Studio UI requires the same acknowledgement before cloning.

If consent is missing or false, the API returns **422** and does not store the
upload.

## What consent is (and is not)

| Consent **is** | Consent **is not** |
|----------------|--------------------|
| A required application gate | Identity verification |
| A recorded boolean on the voice row | Proof of legal ownership |
| A reminder that permission is required | A substitute for your own records |

VoiceForge records the caller’s declaration (`Voice.consent` in SQLite). It
does **not** perform KYC, biometric matching, or third-party verification.

## Operator responsibilities

If you run VoiceForge for others (team, studio, product):

1. Obtain **informed** permission before cloning anyone’s voice.
2. Retain your own evidence of permission outside this service if needed for
   compliance (contracts, written consent, session notes).
3. Do not store personal consent documents that contain sensitive PII in public
   issue trackers or git.
4. Delete voices and wipe `data/` when permission ends or retention expires.

## Optional metadata (not implemented)

Future optional fields under consideration (would remain optional and
backwards-compatible):

- `consent_source` — how permission was obtained
- `consent_note` — free-text operator note (no PII preferred)
- `intended_use` — category such as personal / demo / production

These are **not** required for the current API. Do not assume they exist until
shipped and documented.

## Studio and API behaviour

- Studio: checkbox must be checked before clone starts; the client sends
  `consent=true`.
- API: `consent` is a required form field; only truthy values proceed.
- Deletion: removing a voice does not erase any external consent records you keep.
