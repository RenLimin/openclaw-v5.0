#!/usr/bin/env python3
"""Recursive credential-shape scanner. NEVER prints secret values."""
import json, os, re, sys, hashlib

KEY_PAT = re.compile(
    r'(secret|token|key|password|passwd|pwd|apikey|credential|cred|auth|bearer|'
    r'cookie|session|signature|sign|corpid|corpsecret|appid|appsecret|dsn|'
    r'connectionstring|privatekey|cert)', re.I)

# things that look like a secret ref / indirection, not a plaintext secret
REF_PAT = re.compile(
    r'^(\$\{[^}]+\}|secret://|file://|env:|ENV:|@file:|keychain://|op://|\{\{[^}]+\}\})', re.I)

# obvious non-secret values even under a suspicious key name
BENIGN = re.compile(r'^(true|false|null|none|off|on|auto|default|disabled|enabled|'
                    r'pairing|open|closed|allow|deny|\d+|local|remote)$', re.I)

PLAIN_MARKERS = [
    (re.compile(r'^sk-[A-Za-z0-9_\-]{16,}'), 'OpenAI-style sk-'),
    (re.compile(r'^ghp_[A-Za-z0-9]{20,}'), 'GitHub PAT ghp_'),
    (re.compile(r'^gho_|^ghs_|^ghu_|^ghr_'), 'GitHub token'),
    (re.compile(r'^tvly-'), 'Tavily key'),
    (re.compile(r'^xox[abprs]-'), 'Slack token'),
    (re.compile(r'^AKIA[0-9A-Z]{16}$'), 'AWS access key id'),
    (re.compile(r'^ya29\.'), 'Google OAuth'),
    (re.compile(r'^eyJ[A-Za-z0-9_\-]+\.'), 'JWT'),
    (re.compile(r'^[0-9a-f]{32}$', re.I), '32-hex'),
    (re.compile(r'^[0-9a-f]{40}$', re.I), '40-hex'),
    (re.compile(r'^[0-9a-f]{64}$', re.I), '64-hex'),
    (re.compile(r'^[A-Za-z0-9\-_]{32,}$'), 'long opaque token-charset'),
]

findings = []

def classify(path, val):
    key = path.split('.')[-1]
    key_hit = bool(KEY_PAT.search(key))
    if not isinstance(val, str):
        return
    v = val.strip()
    if not v:
        return
    if BENIGN.match(v):
        return
    is_ref = bool(REF_PAT.match(v))
    shape = None
    for pat, label in PLAIN_MARKERS:
        if pat.match(v):
            shape = label
            break
    long_val = len(v) >= 20
    # skip plain prose / paths / urls unless key name is suspicious
    looks_pathish = v.startswith(('/', './', '~/', 'http://', 'https://')) or ' ' in v
    if not key_hit and not shape:
        return
    if not key_hit and looks_pathish:
        return
    if key_hit and looks_pathish and not shape and not is_ref:
        # e.g. authProfile: "some path" - still report but flag low
        pass
    if not (key_hit or shape):
        return
    if not long_val and not shape and not is_ref:
        # short value under suspicious key: report as SHORT for review
        form = 'SHORT(<20) probably-not-secret'
    elif is_ref:
        form = 'SecretRef/indirection'
    else:
        form = 'PLAINTEXT' + (f' [{shape}]' if shape else '')
    findings.append({
        'path': path,
        'form': form,
        'len': len(v),
        'sha8': hashlib.sha256(v.encode()).hexdigest()[:8],
        'key_name_hit': key_hit,
    })

def walk(node, prefix=''):
    if isinstance(node, dict):
        for k, v in node.items():
            p = f'{prefix}.{k}' if prefix else k
            if isinstance(v, (dict, list)):
                walk(v, p)
            else:
                classify(p, v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            p = f'{prefix}[{i}]'
            if isinstance(v, (dict, list)):
                walk(v, p)
            else:
                classify(p, v)

for f in sys.argv[1:]:
    if not os.path.exists(f):
        print(f'== {f}: MISSING ==')
        continue
    findings.clear()
    try:
        data = json.load(open(f))
    except Exception as e:
        print(f'== {f}: PARSE ERROR {e} ==')
        continue
    walk(data)
    print(f'\n===== {f} =====')
    st = os.stat(f)
    print(f'  mode={oct(st.st_mode)[-4:]} size={st.st_size}')
    if not findings:
        print('  (no credential-shaped fields)')
    plain = [x for x in findings if x['form'].startswith('PLAINTEXT')]
    refs  = [x for x in findings if x['form'].startswith('SecretRef')]
    other = [x for x in findings if x not in plain and x not in refs]
    for label, group in (('PLAINTEXT', plain), ('SECRETREF', refs), ('OTHER/SHORT', other)):
        if group:
            print(f'  --- {label} ({len(group)}) ---')
            for x in sorted(group, key=lambda y: y['path']):
                print(f"    {x['path']:<58} len={x['len']:<4} form={x['form']} sha8={x['sha8']}")
