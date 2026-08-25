#!/usr/bin/env python3
"""Sync CF KV → BWS via SDK.

Runs as a cron. Reads the OAUTH_STATE KV namespace which holds pending
OAuth tokens written by the OAuth Workers, then writes them to BWS via the SDK.

Each entry in KV has shape:
    {key: "LINKEDIN:access_token", value: "<token>"}
or
    {key: "LINKEDIN:issued_at", value: "2026-08-25T15:..."}
    {key: "LINKEDIN:scopes", value: "openid profile email w_member_social"}
    {key: "INSTAGRAM:access_token", value: "<token>"}
    etc.

The script reads all keys matching "LINKEDIN:*" or "INSTAGRAM:*",
writes each to its corresponding BWS secret, then deletes the KV entry.
"""
from bitwarden_sdk import BitwardenClient, ClientSettings, DeviceType
import uuid as _uuid
import urllib.request
import json
import os
import sys

CLOUDFLARE_API_TOKEN = os.environ.get('CF_API_TOKEN')  # from BWS bridge
CLOUDFLARE_ACCOUNT_ID = "9eb1832f3e42a1dbd6ba854f8d6a1cb2"
CF_KV_NAMESPACE = "004ea62ebed54ee6abc10aeb320d32aa"
BWS_TOKEN_PATH = '/opt/data/.hermes/inbox/bws-token.secret'
BWS_ORG_ID_PATH = '/opt/data/.hermes/inbox/org-id.txt'
PROJECT_ID = 'a1d64864-77f9-4e6a-8d6e-b4a90137189a'

# Map from KV key prefix to BWS secret name.
# IMPORTANT: KV keys are lowercase ("linkedin:" / "instagram:") because that's what
# the Workers write. Match exactly.
KV_TO_BWS = {
    'linkedin:access_token': 'LINKEDIN_ACCESS_TOKEN',
    'linkedin:issued_at': 'LINKEDIN_TOKEN_ISSUED_AT',
    'linkedin:scopes': 'LINKEDIN_TOKEN_SCOPES',
    'linkedin:refresh_token': 'LINKEDIN_REFRESH_TOKEN',
    'instagram:access_token': 'META_ACCESS_TOKEN',
    'instagram:long_lived_token': 'META_IG_LONG_LIVED_TOKEN',
    'instagram:issued_at': 'META_TOKEN_ISSUED_AT',
    'instagram:scopes': 'META_TOKEN_SCOPES',
    'instagram:user_id': 'META_IG_USER_ID',
}


def list_kv_keys():
    """List all keys in the CF KV namespace."""
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE}/keys",
        headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return [r['name'] for r in data.get('result', [])]
    except Exception as e:
        print(f"Error listing KV keys: {e}")
        return []


def get_kv_value(key):
    """Get a single value from CF KV."""
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE}/values/{key}",
        headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def delete_kv_key(key):
    """Delete a key from CF KV after successful sync."""
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/storage/kv/namespaces/{CF_KV_NAMESPACE}/values/{key}",
        method="DELETE",
        headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status == 204
    except urllib.error.HTTPError as e:
        print(f"Error deleting KV key {key}: {e.code}")
        return False


def update_bws_secret(bws_key, value):
    """Update a BWS secret using the SDK."""
    token = open(BWS_TOKEN_PATH).read().strip()
    org_id = open(BWS_ORG_ID_PATH).read().strip()
    s = ClientSettings(
        api_url='https://api.bitwarden.com',
        identity_url='https://identity.bitwarden.com',
        user_agent='kv-bws-sync/1.0',
        device_type=DeviceType.SERVER,
    )
    c = BitwardenClient(s)
    c.auth().login_access_token(token, None)
    
    # Find the secret UUID
    r = c.secrets().list(_uuid.UUID(org_id))
    target_id = None
    for sec in r.to_dict()['data']['data']:
        if isinstance(sec, dict) and sec.get('key') == bws_key:
            target_id = sec['id']
            break
    
    if not target_id:
        print(f"  BWS secret {bws_key} not found")
        return False
    
    # Update with project assignment
    r = c.secrets().update(
        _uuid.UUID(org_id),
        target_id,
        bws_key,
        value,
        'synced from CF KV by kv-bws-sync',
        [_uuid.UUID(PROJECT_ID)],
    )
    return r.success


def main():
    keys = list_kv_keys()
    if not keys:
        print("No keys in KV namespace")
        return
    
    synced = 0
    failed = 0
    for kv_key in keys:
        if kv_key not in KV_TO_BWS:
            continue
        
        bws_key = KV_TO_BWS[kv_key]
        value = get_kv_value(kv_key)
        if value is None:
            print(f"  {kv_key}: not found in KV, skipping")
            continue
        
        print(f"  Syncing {kv_key} → {bws_key}...")
        if update_bws_secret(bws_key, value):
            delete_kv_key(kv_key)
            synced += 1
            print(f"    ✓ synced")
        else:
            failed += 1
            print(f"    ✗ failed")
    
    print(f"Done. Synced: {synced}, Failed: {failed}")


if __name__ == '__main__':
    main()
