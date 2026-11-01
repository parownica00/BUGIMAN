# -*- coding: utf-8 -*-
"""Sejf na klucze API: szyfrowanie hasłem tylko bibliotekami standardowymi Pythona.

PBKDF2-HMAC-SHA256 (200k iteracji) -> klucz szyfrujący + klucz MAC,
strumień HMAC-SHA256 w trybie licznika (XOR), integralność HMAC-SHA256 (encrypt-then-MAC).
Bezpieczeństwo zależy od siły hasła - plik z szyfrogramem jest publiczny.
"""
import base64
import hashlib
import hmac
import json
import os

ITERATIONS = 200000


def _keys(password, salt, iterations):
    k = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations, 64)
    return k[:32], k[32:]


def _stream(key, nonce, length):
    out, counter = b'', 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(8, 'big'), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def _b64(b):
    return base64.b64encode(b).decode('ascii')


def encrypt(data, password):
    salt, nonce = os.urandom(16), os.urandom(16)
    ek, mk = _keys(password, salt, ITERATIONS)
    pt = json.dumps(data).encode('utf-8')
    ct = bytes(a ^ b for a, b in zip(pt, _stream(ek, nonce, len(pt))))
    tag = hmac.new(mk, salt + nonce + ct, hashlib.sha256).digest()
    return {'v': 1, 'iter': ITERATIONS, 'salt': _b64(salt), 'nonce': _b64(nonce),
            'ct': _b64(ct), 'tag': _b64(tag)}


def decrypt(blob, password):
    """Zwraca dict z kluczami albo rzuca ValueError przy złym haśle."""
    salt, nonce = base64.b64decode(blob['salt']), base64.b64decode(blob['nonce'])
    ct, tag = base64.b64decode(blob['ct']), base64.b64decode(blob['tag'])
    ek, mk = _keys(password, salt, int(blob.get('iter', ITERATIONS)))
    if not hmac.compare_digest(tag, hmac.new(mk, salt + nonce + ct, hashlib.sha256).digest()):
        raise ValueError('Nieprawidłowe hasło.')
    pt = bytes(a ^ b for a, b in zip(ct, _stream(ek, nonce, len(ct))))
    return json.loads(pt.decode('utf-8'))


def load(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None
