# -*- coding: utf-8 -*-
"""
    pbkdf2
    ~~~~~~

    This module implements pbkdf2 for Python.  It also has some basic
    tests that ensure that it works.  The implementation is straightforward
    and uses stdlib only stuff and can be easily be copy/pasted into
    your favourite application.

    Use this as replacement for bcrypt that does not need a c implementation
    of a modified blowfish crypto algo.

    Example usage:

    >>> pbkdf2_hex('what i want to hash', 'the random salt')
    'fa7cc8a2b0a932f8e6ea42f9787e9d36e592e0c222ada6a9'

    How to use this:

    1.  Use a constant time string compare function to compare the stored hash
        with the one you're generating::

            def safe_str_cmp(a, b):
                if len(a) != len(b):
                    return False
                rv = 0
                for x, y in izip(a, b):
                    rv |= ord(x) ^ ord(y)
                return rv == 0

    2.  Use `os.urandom` to generate a proper salt of at least 8 byte.
        Use a unique salt per hashed password.

    3.  Store ``algorithm$salt:costfactor$hash`` in the database so that
        you can upgrade later easily to a different algorithm if you need
        one.  For instance ``PBKDF2-256$thesalt:10000$deadbeef...``.


    :copyright: (c) Copyright 2011 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import hmac
import hashlib
import sys
import codecs
from struct import Struct
from operator import xor

py_ver = sys.version_info[0]

if py_ver == 2:
    from itertools import izip, starmap
    can_encode = lambda s: isinstance(s, unicode)
elif py_ver == 3:
    from itertools import starmap
    izip = zip
    xrange = range
    can_encode = lambda s: isinstance(s, str)
else:
    raise RuntimeError('unknown python version')

_pack_int = Struct('>I').pack


def pbkdf2_hex(
    data, salt, iterations=1000, keylen=24, hashfunc=None, encoding='utf-8'):
    """Like :func:`pbkdf2_bin` but returns a hex encoded string."""
    result = pbkdf2_bin(
        data, salt, iterations, keylen, hashfunc, encoding='utf-8'
    )

    return codecs.encode(result, 'hex')


def pbkdf2_bin(
    data, salt, iterations=1000, keylen=24, hashfunc=None, encoding='utf-8'):
    """Returns a binary digest for the PBKDF2 hash algorithm of `data`
    with the given `salt`.  It iterates `iterations` time and produces a
    key of `keylen` bytes.  By default SHA-1 is used as hash function,
    a different hashlib `hashfunc` can be provided.
    """
    hashfunc = hashfunc or hashlib.sha1
    if can_encode(data):
        data = data.encode(encoding)
    if can_encode(salt):
        salt = salt.encode(encoding)
    mac = hmac.new(data, None, hashfunc)
    blocks_len = -(-keylen // mac.digest_size) + 1
    return _bin(mac, salt, blocks_len, iterations)[:keylen]


def _bin_py3(mac, salt, blocks_len, iterations):
    def _pseudorandom(x):
        h = mac.copy()
        h.update(x)
        return h.digest()

    buf = b""
    for block in xrange(1, blocks_len):
        rv = u = _pseudorandom(salt + _pack_int(block))
        for i in xrange(iterations - 1):
            u = _pseudorandom(u)
            rv = list(starmap(xor, izip(rv, u)))
        buf += bytes(rv)
    return buf


def _bin_py2(mac, salt, blocks_len, iterations):
    def _pseudorandom(x):
        h = mac.copy()
        h.update(x)
        return map(ord, h.digest())
    buf = []
    for block in xrange(1, blocks_len):
        rv = u = _pseudorandom(salt + _pack_int(block))
        for i in xrange(iterations - 1):
            u = _pseudorandom(''.join(map(chr, u)))
            rv = starmap(xor, izip(rv, u))
        buf.extend(rv)
    return ''.join(map(chr, buf))

_bin = _bin_py3 if py_ver == 3 else _bin_py2

TEST_TEMPLATE = """
Test failed:
 Expected:   %s
 Got:        %s
 Parameters:
  data=%s
  salt=%s
  iterations=%d
"""

def test():
    failed = []
    def check(data, salt, iterations, keylen, expected):
        rv = pbkdf2_hex(data, salt, iterations, keylen)
        if rv != expected:
            s = TEST_TEMPLATE % (
                expected, rv, data, salt, iterations
            )
            print(s)
            failed.append(1)

    # From RFC 6070
    check('password', 'salt', 1, 20,
          b'0c60c80f961f0e71f3a9b524af6012062fe037a6')
    check('password', 'salt', 2, 20,
          b'ea6c014dc72d6f8ccd1ed92ace1d41f0d8de8957')
    check('password', 'salt', 4096, 20,
          b'4b007901b765489abead49d926f721d065a429c1')
    check('passwordPASSWORDpassword', 'saltSALTsaltSALTsaltSALTsaltSALTsalt',
          4096, 25, b'3d2eec4fe41c849b80c8d83662c0e44a8b291a964cf2f07038')
    check('pass\x00word', 'sa\x00lt', 4096, 16,
          b'56fa6aa75548099dcc37d7f03425e0c3')
    # This one is from the RFC but it just takes for ages
    ##check('password', 'salt', 16777216, 20,
    ##      'eefe3d61cd4da4e4e9945b3d6ba2158c2634e984')

    # From Crypt-PBKDF2
    check('password', 'ATHENA.MIT.EDUraeburn', 1, 16,
          b'cdedb5281bb2f801565a1122b2563515')
    check('password', 'ATHENA.MIT.EDUraeburn', 1, 32,
          b'cdedb5281bb2f801565a1122b25635150ad1f7a04bb9f3a333ecc0e2e1f70837')
    check('password', 'ATHENA.MIT.EDUraeburn', 2, 16,
          b'01dbee7f4a9e243e988b62c73cda935d')
    check('password', 'ATHENA.MIT.EDUraeburn', 2, 32,
          b'01dbee7f4a9e243e988b62c73cda935da05378b93244ec8f48a99e61ad799d86')
    check('password', 'ATHENA.MIT.EDUraeburn', 1200, 32,
          b'5c08eb61fdf71e4e4ec3cf6ba1f5512ba7e52ddbc5e5142f708a31e2e62b1e13')
    check('X' * 64, 'pass phrase equals block size', 1200, 32,
          b'139c30c0966bc32ba55fdbf212530ac9c5ec59f1a452f5cc9ad940fea0598ed1')
    check('X' * 65, 'pass phrase exceeds block size', 1200, 32,
          b'9ccad6d468770cd51b10e6a68721be611a8b4d282601db3b36be9246915ec82a')

    raise SystemExit(bool(failed))


if __name__ == '__main__':
    test()
