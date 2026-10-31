# SCIM provisioning

Horilla implements SCIM 2.0 (RFC 7643 / RFC 7644) for **Users**, so an identity
provider (Okta, Microsoft Entra ID, OneLogin, JumpCloud, ...) can create,
update, deactivate and remove employees.

## 1. Set up Horilla

1. Sign in as a **superuser** and open **Settings → Integrations → SCIM Provisioning**.
2. Choose the defaults (department, job position, shift, employee type) given
   to new employees, and what happens when the provider deletes a user.
3. Click **Generate token** and copy it right away. It is shown only once;
   Horilla stores just its hash. **Reset token** replaces it, and the old token
   stops working immediately.
4. Copy the **SCIM base URL**: `https://<your-horilla-host>/scim/v2`.

A company has one SCIM connection. Employees created through it are placed in
that company, and the token can only see employees of that company.

> **Note:** the Okta and Entra steps below follow each vendor's SCIM
> documentation, and the test suite replays the requests Okta and Entra send.
> They have not yet been verified against a live Okta or Entra tenant.

## 2. Okta

In the Okta admin console, create an app integration (or use your existing SAML
app) and turn on **SCIM provisioning**. Then, under **Provisioning →
Integration**:

| Okta setting | Value |
| --- | --- |
| SCIM connector base URL | `https://<host>/scim/v2` |
| Unique identifier field for users | `userName` |
| Supported provisioning actions | Push New Users, Push Profile Updates |
| Authentication Mode | HTTP Header (Bearer token) |
| Authorization | the token from Horilla |

Under **Provisioning → To App**, enable *Create Users*, *Update User
Attributes* and *Deactivate Users*.

Attribute mapping (**To App**):

| Okta attribute | SCIM attribute | Horilla field |
| --- | --- | --- |
| `user.login` | `userName` | login username |
| `user.email` | `emails[type eq "work"].value` | e-mail |
| `user.firstName` | `name.givenName` | first name |
| `user.lastName` | `name.familyName` | last name |
| `user.mobilePhone` | `phoneNumbers[type eq "work"].value` | phone |
| `user.title` | `title` | job position (matched by name) |
| `user.department` | `urn:...:enterprise:2.0:User:department` | department (matched by name) |
| `user.employeeNumber` | `urn:...:enterprise:2.0:User:employeeNumber` | badge ID |
| `user.managerId` | `urn:...:enterprise:2.0:User:manager.value` | reporting manager |

## 3. Microsoft Entra ID

Under **Enterprise applications → New application → Create your own
application** (non-gallery), open **Provisioning**, set **Provisioning Mode**
to *Automatic*, and enter:

| Entra setting | Value |
| --- | --- |
| Tenant URL | `https://<host>/scim/v2` |
| Secret Token | the token from Horilla |

Click **Test Connection**, then check the mappings under **Mappings →
Provision Microsoft Entra ID Users**:

| Entra attribute | SCIM attribute | Horilla field |
| --- | --- | --- |
| `userPrincipalName` | `userName` | login username |
| `mail` | `emails[type eq "work"].value` | e-mail |
| `givenName` | `name.givenName` | first name |
| `surname` | `name.familyName` | last name |
| `mobile` or `telephoneNumber` | `phoneNumbers[type eq "work"].value` | phone |
| `jobTitle` | `title` | job position (matched by name) |
| `department` | `urn:...:enterprise:2.0:User:department` | department (matched by name) |
| `employeeId` | `urn:...:enterprise:2.0:User:employeeNumber` | badge ID |
| `manager` | `urn:...:enterprise:2.0:User:manager` | reporting manager |
| `Switch([IsSoftDeleted], ...)` | `active` | login enabled / archived |
| `objectId` | `externalId` | stored on the link |

Remove mappings for attributes Horilla doesn't use (for example `addresses`)
to keep the provisioning logs clean.

## 4. Behaviour

- **Required:** `userName` and an e-mail address (taken from `userName` when it
  is an e-mail and no `emails` are sent). A first name is derived from
  `displayName` or `userName` when `name.givenName` is missing.
- **Department and title** are matched by name against this company's (or
  shared) departments and job positions. A name that doesn't match leaves the
  current value unchanged.
- **Manager** must be a user provisioned by the same connection. An unknown
  manager is ignored until the provider sends it again. A user can't be their
  own manager, and reporting loops are refused.
- **`active: false`** disables login immediately and archives the employee. If
  they still manage people or processes, only the login is disabled and
  superusers are notified to reassign and archive.
- **`active: true`** only reactivates employees the provider deactivated,
  unless *Allow the identity provider to reactivate archived employees* is on.
- **DELETE** archives the employee and unlinks them, or, with the permanent
  delete mode, deletes the employee and their data. It falls back to archiving
  when other records still reference them.
- **PUT merges:** attributes left out of a PUT keep their current value. Okta
  only sends the attributes you mapped, so a full replace would erase values
  HR maintains in Horilla. To clear an attribute, send it empty or PATCH
  `remove` it.
- **PATCH `remove`** clears optional attributes (phone, title, department,
  manager, employee number, family name, `externalId`). Removing `userName`,
  `emails`, `name.givenName` or `active` is refused with `400 mutability`.
- **Filters:** `eq` only, on `id`, `externalId`, `userName` and `emails.value`,
  up to 512 characters.
- **Uniqueness:** e-mail and `userName` are unique across the installation, so
  `POST` answers `409 uniqueness` when they belong to another company.
- **Superusers** are never changed by a provider.
- **Not supported:** Groups, bulk operations, sorting, ETags and password
  changes.
- **Rate limit:** the `scim` throttle scope, `THROTTLE_SCIM` (default
  `1200/min`).

The **Recent requests** log on the settings page shows each call's status and
error detail, with filter values redacted. Entries are kept for 30 days.
