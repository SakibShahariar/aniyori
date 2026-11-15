# AniList account setup and sync

Aniyori uses one project-owned AniList OAuth application. Users should not create their own application or share an AniList password.

## Project owner setup

1. Open AniList Developer Settings at https://anilist.co/settings/developer and create the Aniyori application.
2. Set its Redirect URL to exactly:

   https://anilist.co/api/v2/oauth/pin

3. Save the numeric public Client ID and provide it to the project maintainer so it can be bundled with the application.
4. Do not put the Client Secret in Aniyori, source control, release files, or user configuration. The desktop app uses AniList's Implicit Grant/Auth Pin flow and does not need the secret.

Until the project Client ID is bundled, development builds expose a Client ID field in Main menu → AniList Account for maintainer setup. End users should use the project-owned ID once it is included in a release.

## Connect an account

1. Open Main menu → AniList Account.
2. Select Open AniList Authorization.
3. Sign in to AniList and approve Aniyori.
4. Copy the access token displayed on the Auth Pin page and paste it into Aniyori.
5. Select Connect Account. Aniyori validates the token against the authenticated AniList account before storing it.

Access tokens are stored through the desktop Secret Service using secret-tool. If the keyring is unavailable, connection fails rather than writing the token to a plain-text configuration file. The settings file contains only the public Client ID and account label.

AniList access tokens last about one year and do not have refresh tokens. When a token expires, reconnect the account through the same authorization flow. Disconnecting removes the stored token; it does not delete the local library.

## Import and sync

- Import AniList Library adds entries that are not already linked by AniList media ID. Existing local entries are left unchanged.
- Review Sync previews new entries and identifies differing progress/status values before applying changes.
- Each differing entry requires an explicit choice: keep the local value and update AniList, or use the AniList value and update the local entry.
- Local-only entries remain local unless you explicitly choose to add them back to AniList.
- Entries that already match are left alone. Manual entries without an AniList media ID are not automatically linked by title.

The current implementation treats every mismatch as a conflict because it does not yet keep a last-synchronized snapshot. This is intentionally conservative: it may ask you to resolve a difference even when only one side changed, but it will not silently overwrite either side.

Aniyori's local library remains available when disconnected or offline. Only account import and synchronization require AniList connectivity.
