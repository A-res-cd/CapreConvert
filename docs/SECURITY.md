# Security

Bind 127.0.0.1 by default. Bootstrap in URL fragment, short-lived and single-use. Explicit
--lan binds LAN and rotates strong pairing token on every launch. Credentials never enter
access logs; session cookies HttpOnly/SameSite Strict, Secure with TLS. Persist opaque
session owners across restarts. Pairing is rate limited. Validate Host, exact Origin and
CSRF on mutations. Disable CORS, API doc CDNs and forwarded-header trust.

Private workspace, generated IDs/paths, atomic manifests, exclusive workspace lock.
New Windows workspace roots receive an ACL for the current user and SYSTEM; POSIX roots
use mode 0700. Refuse nonempty unrecognized workspace directories. Private manifests store
hashed session cookies and owned job IDs. Retained JPEGs carry SHA-256 checksums validated
at startup; uncommitted outputs and staging files are removed during recovery.
ZIP validation rejects traversal, absolute/drive/UNC/ADS paths, NULs, Windows device names,
links, special types, encryption and bombs. Never extractall. Case/Unicode collisions
resolve deterministically. Foreign resources always 404. Downloads protect files from deletion.

LAN HTTP has no transport confidentiality. Use a trusted private LAN or configure TLS.
Allow Windows firewall only on private networks manually. Check same Wi-Fi, guest/client
isolation, VPN, wrong interface/IP, host sleep, and interrupted background mobile uploads.
No automatic firewall/router modification and no public exposure.
