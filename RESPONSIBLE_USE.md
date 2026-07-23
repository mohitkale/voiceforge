# Responsible use

VoiceForge is a self-hosted voice cloning studio and API. Cloning technology
can be misused for impersonation, fraud, harassment, and deception.

## Allowed use

Clone **only**:

- your own voice, or
- a voice for which you have **clear, informed, and valid permission**

Operators (anyone running VoiceForge) are responsible for obtaining and
retaining evidence of that permission. The application does not verify identity
or legal authority.

## Prohibited use

Do **not** use VoiceForge to:

- impersonate someone without permission
- commit fraud or social-engineering attacks
- harass, threaten, or coerce anyone
- bypass identity verification or voice-based authentication
- mislead people about the origin of generated audio
- create or distribute deceptive deepfakes of public figures or private individuals

## Consent declaration (application control)

Creating a voice requires `consent=true` (API) or the Studio consent checkbox.
That field records the caller’s **declaration**, not proof of ownership.

See [docs/CONSENT.md](docs/CONSENT.md) for details and operator guidance.

## Disclosure

Where context requires it (publications, products, social media, customer
communications), disclose that speech was generated or cloned with AI.

## Privacy and deletion

- Voice samples and generated artifacts stay on infrastructure **you** choose
  (workstation, private server, or GPU environment you control).
- Deleting a voice via `DELETE /v1/voices/{id}` removes the database row and the
  on-disk voice directory (samples, artifacts, preview).
- Wipe Docker volumes / `data/` when retiring a deployment.

## Watermarking

Optional synth watermarking is a **weak, voice-specific fingerprint**. It is
**not** forensic proof, not a substitute for consent, and not guaranteed to
survive recompression or editing. See [docs/WATERMARKING.md](docs/WATERMARKING.md).

## Security incidents

If you discover a vulnerability or a voice-data incident related to this
project, report it privately — see [SECURITY.md](SECURITY.md). Do not attach
private voice samples or API tokens to public issues.
