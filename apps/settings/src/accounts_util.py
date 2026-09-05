import ctypes
import ctypes.util
import secrets

# crypt(3) salt alphabet (RFC-ish: '.', '/', 0-9, A-Z, a-z).
_SALT_CHARS = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


def crypt_password(plaintext: str) -> str:
    """AccountsService's SetPassword D-Bus method wants the password already
    crypt(3)-hashed -- its own introspection XML says so ("The crypted
    password."). Handing it plaintext writes that string into /etc/shadow as
    the hash field verbatim: `chpasswd -e` then errors (surfaces to the user
    as a D-Bus error) or, worse, stores it and every later login fails as if
    no password were ever set.

    Python 3.13 removed the stdlib `crypt` module, so call libcrypt directly.
    $6$ selects SHA-512, the /etc/shadow default on Ubuntu; 16 salt chars is
    what `mkpasswd`/`openssl passwd -6` use.
    """
    salt = '$6$' + ''.join(secrets.choice(_SALT_CHARS) for _ in range(16))
    libcrypt = ctypes.CDLL(ctypes.util.find_library('crypt') or 'libcrypt.so.1')
    libcrypt.crypt.restype = ctypes.c_char_p
    libcrypt.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    hashed = libcrypt.crypt(plaintext.encode('utf-8'), salt.encode('ascii'))
    if not hashed or not hashed.startswith(b'$6$'):
        raise RuntimeError('crypt() did not return a SHA-512 hash')
    return hashed.decode('ascii')
