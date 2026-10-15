"""Public keys this build trusts to sign release manifests.

EMBEDDED on purpose: a key read from a file in the data folder could be
replaced by whoever can write there, and then any manifest would "verify".

This list is EMPTY until the release owner generates the production key:

    python scripts/release/generate_signing_key.py --key-id spj-release-2026a \
        --out <ruta FUERA del repositorio>/spj-release-2026a.pem

The script prints the `TrustedKey(...)` line to paste below. The private key
goes to the signing machine / CI secret `SPJ_MANIFEST_SIGNING_KEY` and is never
committed. With an empty list the application refuses every online and offline
update with an explicit message — it never falls back to "unsigned is fine".

Rotation (planned, no downtime):

1. Generate the new key and add it here NEXT to the current one.
2. Ship one release signed by the CURRENT key that contains both keys.
3. From then on sign with both keys (the envelope accepts several
   signatures), then only with the new one.
4. Mark the old key `revoked=True` in a later release. A compromised key is
   marked revoked immediately and a release signed with the other key is
   pushed as mandatory.
"""
from __future__ import annotations

from backend.infrastructure.updater.update_manifest import TrustedKey, TrustedKeyring

EMBEDDED_RELEASE_KEYS: tuple[TrustedKey, ...] = (
    # TrustedKey("spj-release-2026a", "<base64 Ed25519 public key>",
    #            note="Clave de producción 2026"),
)


def embedded_keyring() -> TrustedKeyring:
    return TrustedKeyring(EMBEDDED_RELEASE_KEYS)
