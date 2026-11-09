# Desktop installation and updates

Implement v1.1.1 in this order:

1. Keep update networking outside the server and conversion workers. Only explicit host CLI
   actions contact the fixed public GitHub repository A-res-cd/CapreConvert.
2. Install complete bundles per-user, side by side, separate from workspaces. Create Desktop
   and Start-menu launch/update shortcuts. Retain older versions; use an atomic current pointer.
3. Validate release metadata, exact asset URLs/names, bounded downloads and checksums. Inspect
   every ZIP entry before bounded streaming into a private staging folder; never extract paths
   chosen unchecked by an archive. Verify the candidate CLI before activating it.
4. Test hostile archives, interrupted updates, rollback, offline/no-release responses and
   actual Windows shortcuts/installed launching. Run conversion regressions.
5. Build v1.1.1, execute frozen checks and record release artifacts and remaining limits.

No automatic background update, credentials, administrator installation, workspace migration,
running-app termination or GitHub publication. Internet is optional and only required for
the user-requested updater. Future releases must attach the standard Windows ZIP and SHA-256.
