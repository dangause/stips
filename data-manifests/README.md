# Data Manifests

Versioned pointers to external data bundles (refcats, defects, templates,
archive pulls). Populate the URLs/checksums before use; CI should consume the
“lite” bundles while production fetches the full ones.

Suggested workflow:

1. Edit the manifest entry with the new bundle version + checksum.
2. Upload the bundle to your object store.
3. Run the fetcher (to be added under `archive_tools`) to download/verify into
   `${OBS_NICKEL_DATA:-$HOME/.cache/obs_nickel}`.
4. Commit the manifest change alongside the code/config that expects it.
