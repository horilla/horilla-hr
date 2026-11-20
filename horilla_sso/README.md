# Single Sign-On — Setup Guide (Microsoft And Google)

This guide has two parts: **Sign In With Microsoft** (first) and **Sign In With Google (Workspace)** (further down). You can turn on one or both; each adds its own button to the login page.

# Sign In With Microsoft

This lets your employees sign in to Horilla with their Microsoft work account, with no separate Horilla password to remember.

You set it up in **two places**:

1. **Microsoft Azure (Entra ID)** — you tell Microsoft that Horilla is allowed to ask for sign-ins.
2. **Horilla** — you paste three values from Azure into one settings page.

It takes about 15 minutes. It does **not** cost anything: the free Microsoft Entra plan is enough.

---

## Before You Start

You need:

- A Microsoft account that can open [entra.microsoft.com](https://entra.microsoft.com) and **create app registrations**. If "New registration" is greyed out, ask your Microsoft 365 admin to do Part 1 for you, or to give you the *Application Developer* role.
- A Horilla **superuser** login.
- The web address of your Horilla, for example `https://hr.yourcompany.com` (for a test on your own computer: `http://localhost:8000`).

> **Important for companies:** the Microsoft directory behind your company email must be a *managed* directory, meaning your email domain was verified with Microsoft. If it is not, Microsoft refuses the sign-in with the message *"…is in an unmanaged state… needs to claim ownership of the company by DNS validation"* (error `AADSTS650051`). Whoever controls your domain's DNS can fix this under Entra → **Domain names**.

---

## Part 1 — Azure Side

### Step 1: Register the app

1. Open [entra.microsoft.com](https://entra.microsoft.com) and sign in.
2. In the left menu click **App registrations**, then **New registration**.
3. Fill in the form:

| Field | What to enter |
|---|---|
| **Name** | `Horilla Sign-In` (any name you like; users see it on the Microsoft sign-in screen) |
| **Supported account types** | **Company use:** *Single tenant only* (only people in your own directory can sign in). **Testing with a personal account (outlook.com, hotmail.com, Gmail registered with Microsoft):** *Multitenant and personal Microsoft account* |
| **Redirect URI** | Platform **Web**, and this address exactly: `https://YOUR-HORILLA-ADDRESS/login/microsoft/callback/` |

4. Click **Register**.

> The redirect address must match **exactly**, including `https`, the port (if any) and the **slash at the end**. Microsoft only allows plain `http` for `localhost`.

### Step 2: Copy two values

You are now on the app's **Overview** page. Copy and keep:

- **Application (client) ID**
- **Directory (tenant) ID**

### Step 3: Create a client secret

1. Open **Certificates & secrets → Client secrets → New client secret**.
2. Give it a name, for example `Horilla`, and choose how long it lasts (**24 months is the longest**).
3. Click **Add**.
4. **Copy the _Value_ column straight away.** Microsoft shows it only once. Do **not** copy the *Secret ID* column — that is a different thing and will not work.

> Write down the expiry date. When the secret expires, nobody can sign in with Microsoft until you create a new one and paste it into Horilla (Part 2).

### Step 4: Check nothing else is needed

- **API permissions:** leave the default (`User.Read`). No admin approval is needed.
- **Optional:** under **Token configuration → Add optional claim → ID**, add `email`. Horilla works without it, but it makes matching more reliable.
- **If Azure complains about the access token version** when you save the account type, open **Manifest** and set `requestedAccessTokenVersion` to `2` (older manifests call it `accessTokenAcceptedVersion`), then save.

---

## Part 2 — Horilla Side

### Step 1: Open the settings page

Sign in as a superuser, then go to **Settings → Integrations → Microsoft Sign-In**.

The page shows a **Redirect URI** box. This is the address Microsoft must be told about. If it differs from what you entered in Azure, fix Azure (or open Horilla using the address you registered).

### Step 2: Fill in the form

| Field | What to enter |
|---|---|
| **Enable Microsoft Sign-In** | Turn **on** |
| **Tenant ID** | **Company (single tenant):** paste the *Directory (tenant) ID* from Azure. **Work accounts from any company:** `organizations`. **Work and personal accounts (testing):** `common` |
| **Client ID** | The *Application (client) ID* from Azure |
| **Client Secret** | The secret **Value** from Azure (see Part 1, Step 3). The saved secret is filled in on later visits; click the eye icon to show it |
| **Allowed Email Domains** | Optional. For example `yourcompany.com`. Leave empty to allow any domain. Separate several with commas |
| **Hide Password Sign-In** | Optional. One switch shared by Microsoft and Google. Turn on once sign-in works and you want only the sign-in buttons on the login page |

Click **Save**.

**What the settings page checks for you:** the Client ID must be Azure's long ID (like `12345678-1234-…`), the secret must not be the *Secret ID* or contain spaces, domains must be plain domains such as `contoso.com` (not email addresses), and *Hide Password Sign-In* can only be on when a sign-in provider (Microsoft or Google) is enabled.

### Step 3: Make sure each person exists in Horilla

Microsoft sign-in **does not create employees**. Each person must already be an active employee in Horilla, and **their Microsoft sign-in address must match their Horilla email**:

- Horilla checks the employee's **Email** first, then their **Work Email**.
- If someone signs in to Microsoft as `first.last@company.com` but their Horilla email is different, put the Microsoft address in their **Work Email**.
- If two employees have the same email, the sign-in is refused instead of guessing.

### Step 4: Try it

1. Log out of Horilla.
2. On the login page, click **Sign In With Microsoft**.
3. Choose your Microsoft account. You land on the Horilla dashboard.

The button only appears when Microsoft sign-in is **enabled and fully filled in**.

---

## Good To Know

- **First sign-in:** people who sign in with Microsoft are not asked to set a Horilla password, and the two-step code for Horilla's own login is skipped (Microsoft already verified them).
- **Password login still works** unless you turn on *Hide Password Sign-In*. Even then, a small **Sign In With Password** link under the Microsoft button opens the password form, so an administrator can never be locked out.
- **Limit who can sign in (optional):** in Entra open **Enterprise applications → Horilla Sign-In → Properties**, set **Assignment required** to **Yes**, then add people under **Users and groups**. Without this, everyone in your directory can reach the Microsoft sign-in, but Horilla still lets in only matching employees.
- **Single directory is the safest setup.** With the *Directory (tenant) ID* only people from that one directory can sign in. If you use `organizations` or `common`, people from any Microsoft directory can reach the sign-in, so Horilla then matches them **only by their sign-in name** (the user principal name), never by the `email` claim, which each directory's own admin can type freely.
- **Several environments (test and live):** add each address as its own **Web** redirect URI in Azure (**Authentication**).
- **The secret is stored encrypted** in the Horilla database. Anyone who opens the settings page as a superuser can reveal it, so keep that page to administrators.

---

## If Something Goes Wrong

When Microsoft refuses a sign-in, the Horilla login page shows Microsoft's own reason after *"The Microsoft Sign-In Was Not Completed."*

| What you see | What it means | What to do |
|---|---|---|
| `AADSTS650051` … *unmanaged state* | The company's domain is not verified with Microsoft | A DNS owner verifies the domain in Entra → **Domain names** |
| *Selected user account does not exist in tenant 'Microsoft Services'* | A personal account is signing in to an app that only allows company accounts | In Azure → **Authentication → Supported accounts**, choose the option that includes personal accounts, and use Tenant ID `common` in Horilla |
| `AADSTS50011` — reply URL does not match | The redirect address is different in Azure and Horilla | Make the **Web** redirect URI in Azure exactly the one shown on the Horilla settings page (including the final `/`) |
| `AADSTS7000215` — invalid client secret | The wrong value was pasted, or it expired | Create a new secret and paste its **Value** (not the Secret ID) |
| `AADSTS700016` — application not found | Wrong Client ID or wrong Tenant ID | Re-copy both from the Azure **Overview** page |
| `AADSTS65001` / *needs admin approval* | Your organisation requires an admin to approve new apps | Ask a Microsoft 365 admin to grant consent for *Horilla Sign-In* |
| *Microsoft Could Not Be Reached. Please Try Again.* | Horilla could not contact Microsoft (network, firewall or Microsoft outage) | Check the server's internet access to `login.microsoftonline.com`, then try again |
| *No Employee Matches This Microsoft Account.* | Signed in to Microsoft correctly, but no active Horilla employee has that email | Add or correct the employee's Email or Work Email |
| *This Microsoft Account Is Not Allowed To Sign In.* | The email domain is not in **Allowed Email Domains** | Add the domain, or leave the field empty |
| *This User Is Archived…* | The employee is archived in Horilla | Re-activate the employee |
| *The Microsoft Sign-In Could Not Be Verified.* | The sign-in expired, was opened in two tabs, or came from the wrong directory | Try again from the Horilla login page. For a single-tenant app, make sure the account belongs to that directory |
| No Microsoft button on the login page | Not enabled, or a field is empty | Check **Enable Microsoft Sign-In**, Tenant ID, Client ID and Client Secret are all filled in |

Still stuck? In Entra, open **Monitoring & health → Sign-in logs** and search for the **Correlation ID** shown on Microsoft's error page. It gives the exact reason.

---

## Quick Checklist

- [ ] App registered in Azure with the right account type
- [ ] Redirect URI (Web) added, exactly matching Horilla's settings page
- [ ] Client ID, Tenant ID and secret **Value** copied
- [ ] Secret expiry date written down
- [ ] Horilla: enabled, three values filled in, saved
- [ ] Every user exists as an active employee with a matching email
- [ ] Tested with one real account

---
---

# Sign In With Google (Workspace)

This lets employees sign in to Horilla with their **Google Workspace** account (for example `ada@yourcompany.com`). It works for **Workspace domains only**: a personal `@gmail.com` account can never sign in, even if an employee has that Gmail address in Horilla. It costs nothing.

You set it up in **two places**: the Google Cloud Console, and one Horilla settings page.

## Before You Start

- A Google account that can open [console.cloud.google.com](https://console.cloud.google.com) (a Workspace admin is best, because the consent screen below is for your organisation).
- A Horilla **superuser** login.
- The web address of your Horilla, for example `https://hr.yourcompany.com` (for a test on your own computer: `http://localhost:8000`).

## Part 1 — Google Cloud Side

### Step 1: Create or pick a project

1. Open [console.cloud.google.com](https://console.cloud.google.com).
2. At the top, open the project list and click **New project** (name it `Horilla Sign-In`), or pick an existing one.

### Step 2: Set up the consent screen

1. Open **APIs & Services → OAuth consent screen** (newer consoles call it **Google Auth Platform → Branding / Audience**).
2. **User type / Audience:** choose **Internal**. Only people in your Workspace can then sign in, and no Google review is needed. (**External** also works, but Horilla still lets in only your Workspace domains.)
3. Enter an app name (users see it on Google's sign-in screen) and a support email, then save.
4. **Scopes:** the defaults (`openid`, `email`, `profile`) are enough.

### Step 3: Create the OAuth client

1. Open **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. **Application type:** **Web application**. Name it `Horilla`.
3. Under **Authorized redirect URIs** click **Add URI** and enter this address exactly: `https://YOUR-HORILLA-ADDRESS/login/google/callback/`. It must match **exactly**, including `https`, the port (if any) and the **slash at the end**. Google only allows plain `http` for `localhost`.
4. Click **Create**.
5. Copy the **Client ID** (it looks like `1234567890-abc123.apps.googleusercontent.com`) and the **Client secret** (it starts with `GOCSPX-`).

## Part 2 — Horilla Side

1. Sign in as a superuser and go to **Settings → Integrations → Google Sign-In**.
2. The **Authorized Redirect URI** box shows the address Google must be told about. If it differs from the one you entered in Google, fix Google (or open Horilla using the address you registered).
3. Fill in the form:

| Field | What to enter |
|---|---|
| **Enable Google Sign-In** | Turn **on** |
| **Client ID** | The Client ID from Google (ends in `.apps.googleusercontent.com`) |
| **Client Secret** | The Client secret from Google. The saved secret is filled in on later visits; click the eye icon to show it |
| **Allowed Workspace Domains** | **Required.** Your Workspace domain, for example `yourcompany.com`. Separate several with commas |
| **Hide Password Sign-In** | Optional. The same shared switch as on the Microsoft page |

4. Click **Save**.

**What the settings page checks for you:** the Client ID must look like Google's (`…apps.googleusercontent.com`), the secret must not be the Client ID or contain spaces, domains must be plain domains (not email addresses), and Google sign-in cannot be enabled without at least one domain.

### Make sure each person exists in Horilla

Google sign-in **does not create employees**. Each person must already be an active employee whose Horilla **Email** (or **Work Email**) matches their Google Workspace address. If two employees share the same email, the sign-in is refused instead of guessing.

### Try it

Log out, click **Sign In With Google** on the login page, and choose your Workspace account. The button only appears when Google sign-in is **enabled with a client, a secret and at least one domain**.

## How Horilla Decides Who May Sign In

Horilla accepts a Google sign-in only when **all** of these are true:

1. The sign-in is a genuine one that started from this browser, for this app, and has not expired or been replayed.
2. Google says the email is **verified**.
3. The account belongs to a **Workspace domain** (Google's `hd` value) that is in **Allowed Workspace Domains**, and the email address is on that same domain. A Gmail address can never pass, even one that looks like your company's.
4. An active Horilla employee has that email.

People who sign in with Google are not asked to set a Horilla password, and Horilla's own two-step code is skipped (Google already verified them).

## If Something Goes Wrong

| What you see | What it means | What to do |
|---|---|---|
| `redirect_uri_mismatch` on Google's page | The redirect address differs between Google and Horilla | Make the **Authorized redirect URI** in Google exactly the one on the Horilla settings page (including the final `/`) |
| `Error 403: org_internal` | The consent screen is *Internal* and the person is outside your Workspace | Use a Workspace account, or switch the consent screen to *External* |
| `invalid_client` / *The Google Sign-In Was Not Completed* | Wrong Client ID or secret | Re-copy both from **Credentials** |
| *Google Could Not Be Reached. Please Try Again.* | Horilla could not contact Google (network or firewall) | Check the server's internet access to `oauth2.googleapis.com` |
| *This Google Account's Email Is Not Verified.* | Google has not verified that address | Use a verified Workspace account |
| *This Google Account Is Not Allowed To Sign In.* | Not a Workspace account, or its domain is not in **Allowed Workspace Domains** | Add the domain, or sign in with a Workspace account |
| *No Employee Matches This Google Account.* | Signed in to Google correctly, but no active employee has that email | Add or correct the employee's Email or Work Email |
| *This User Is Archived…* | The employee is archived in Horilla | Re-activate the employee |
| *The Google Sign-In Could Not Be Verified.* | The sign-in expired or was opened in two tabs | Try again from the Horilla login page |
| No Google button on the login page | Not enabled, or a field (including the domain) is empty | Check all fields on the Google Sign-In page |

## Quick Checklist

- [ ] Google Cloud project, consent screen (*Internal*) and a **Web application** OAuth client created
- [ ] Authorized redirect URI added, exactly matching Horilla's settings page
- [ ] Client ID and Client secret copied
- [ ] Horilla: enabled, client, secret and at least one Workspace domain filled in, saved
- [ ] Every user exists as an active employee with a matching email
- [ ] Tested with one real Workspace account
