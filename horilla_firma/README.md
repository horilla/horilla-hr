# Firma E-Signature (`horilla_firma`)

Optional integration that sends offer letters to candidates for electronic
signature with [Firma](https://firma.dev), and brings the signed document back
to the candidate's profile.

Nothing is sent and no tab is shown until an administrator switches the
integration on and saves a Firma API key.

## What it adds

- **Settings, E-Signature, Firma E-Signature**: the Firma API key and the
  webhook signing secret (both stored encrypted with a key derived from
  `SECRET_KEY`, the same scheme as `horilla_sso`), a default expiration, Test
  Connection and Register Webhook.
- **Candidate profile, E-Signatures tab**: the candidate's signature requests
  with their status, and **Send for Signature**, which sends either
  - a Firma template that has exactly one signer or approver (the candidate
    fills that role), or
  - an offer letter PDF rendered from a Horilla mail template (the same
    rendering as Send Mail attachments), with one signature box on the last
    page.
- **Webhook** at `/firma/webhook/` that moves each request forward (Sent, In
  Progress, Signed, Declined, Cancelled, Expired).
- **Scheduled jobs** (`manage.py run_scheduler`) that download the signed PDF of
  completed requests every 5 minutes, with back-off, and mark interrupted sends
  as Outcome Unknown; a **Refresh** action reads the status from Firma and
  fetches the PDF on demand.

## Setup

1. In the Firma dashboard (https://app.firma.dev), create an API key under
   Settings, API Keys.
2. In Horilla, open Settings, E-Signature, Firma E-Signature. Paste the API key,
   switch the integration on, and Save. Use Test Connection to check the key.
3. For status updates and signed documents:
   - In the Firma dashboard, open Settings, Webhook Configuration, switch
     **Enable Webhooks** on and copy the **Webhook Signing Secret** into the
     Horilla settings. Firma delivers company webhooks only while Enable
     Webhooks is on; it is off by default and cannot be changed through the
     API. A test delivery from Firma is sent even when the switch is off, so a
     successful test does not prove that real events will arrive.
   - Open the Horilla settings through its public HTTPS address and press
     Register Webhook. An existing Firma webhook for the same address is
     reused, and enabled again (with any missing events added) when Firma had
     disabled it.
   - Run the scheduler (`python manage.py run_scheduler`) so signed PDFs are
     downloaded. Without webhooks, use Refresh on the E-Signatures tab.

## Permissions

| Action | Needs |
| --- | --- |
| Settings page, Register Webhook, Link | `horilla_firma.change_firmasettings` (superusers have it) |
| See the E-Signatures tab | whoever may view the candidate |
| Send for Signature, Refresh | `recruitment.change_candidate` |

The signed PDF is stored with `horilla.models.upload_path`, so
`base/media_access.py` applies its per-file rules. The signature request hangs
from the candidate only (the mail template is kept by title, not linked), so
the signed PDF is readable by whoever may view, created or manages the
candidate, its recruitment or its stage, by the person who sent it, and by
holders of `horilla_firma.view_firmasignaturerequest`, never through the mail
template. The candidate has no reverse link to these requests, so they never
widen access to the candidate's own files.

## Sending safely

- A send is attempted at most once per opened form. The request row is written
  before the call to Firma, so a double click, a replayed submission or a
  second send for the same candidate while one is in flight is refused.
- Only a definite refusal from Firma (a 4xx answer, 429, or a 503 with
  Firma's `ANCHOR_DISABLED_EDGE` / `SEALS_DISABLED` code) is reported as
  "nothing was sent". Any other failure (timeouts, gateway errors, a 5xx) is
  recorded as **Outcome Unknown** and is never retried: check the Firma
  dashboard, and an administrator can link the Firma request ID to the row.
  Linking refuses a Firma request whose signers and approvers do not include
  the row's recipient email. The next send to that candidate asks for
  confirmation first.
- A send interrupted before Firma's answer was recorded (for example a worker
  timeout) also becomes **Outcome Unknown** after 5 minutes: when the tab or
  the send form is opened, and in the scheduled job.
- The request row must be committed before the call to Firma, so a send
  started inside a database transaction is refused before anything is sent.
  The send view opts out of `ATOMIC_REQUESTS`, so sending also works when the
  database is configured with it (for example `?atomic_requests=true` in
  `DATABASE_URL`).
- When Firma answers that the request was already sent (409 `ALREADY_SENT`,
  `SEND_EFFECTS_EXIST`), the existing Firma request is recorded instead of
  sending again.
- Firma silently drops a recipient that matches no role of a template, so a
  template with more than one signing role is not offered, and the template is
  read again just before sending.
- Offer letter PDFs up to 4 MiB are sent inline; larger ones go through
  Firma's presigned upload.

## Webhook security

The endpoint verifies `X-Firma-Signature` (`t=<unix seconds>,v1=<hex>`,
HMAC-SHA256 over `<t>.<raw body>`) with the saved secret, accepts
`X-Firma-Signature-Old` during secret rotation, refuses signatures older than 5
minutes, and refuses everything when no secret is saved. Each event is
processed once (by its `id`), and the endpoint answers immediately; the signed
PDF is downloaded by the scheduled job, never inside the delivery. Events for
requests that Horilla did not send are acknowledged and ignored.

## Tests

```sh
python manage.py test horilla_firma
```

The Firma API is mocked in every test.

## Links

- Firma API documentation: https://docs.firma.dev
- Privacy policy: https://firma.dev/legal/privacy-policy
- Terms: https://firma.dev/legal/terms-conditions
- Support: support@firma.dev
