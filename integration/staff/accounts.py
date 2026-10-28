"""Local staff accounts: scrypt hashes in .runtime/staff, never sent to n8n or the database."""
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import threading

ROLES = {'ADMIN', 'MUNICIPALITY', 'UTILITY'}
USERNAME = re.compile(r'[a-z][a-z0-9._-]{2,31}')
ORGANISATION = re.compile(r'[A-Z][A-Z0-9_]{1,39}')


class AccountError(ValueError):
    """Message is safe to show to the administrator."""


def _hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, maxmem=64 * 1024 * 1024).hex()


def check_password(password):
    if not isinstance(password, str) or not 10 <= len(password) <= 200:
        raise AccountError('The password must contain between 10 and 200 characters.')


class Accounts:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        # Comparing against a dummy hash keeps unknown usernames as slow as wrong passwords.
        self.dummy = (secrets.token_bytes(16), _hash(secrets.token_urlsafe(16), b'0' * 16))

    def _load(self):
        if not self.path.is_file():
            return {}
        return json.loads(self.path.read_text(encoding='utf-8'))['accounts']

    def _save(self, accounts):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps({'format': 1, 'accounts': accounts}, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(self.path)

    @staticmethod
    def public(username, record):
        return {'username': username, 'display_name': record['display_name'], 'role': record['role'],
                'organisation': record['organisation'], 'active': record['active'],
                'pending': record.get('pending', False), 'request_note': record.get('request_note')}

    def has_admin(self):
        return any(r['role'] == 'ADMIN' and r['active'] for r in self._load().values())

    def list(self):
        return [self.public(u, r) for u, r in sorted(self._load().items())]

    def create(self, username, display_name, password, role, organisation, request_note=None):
        """request_note set = self-registration: inactive and pending until an admin approves."""
        if not isinstance(username, str) or not USERNAME.fullmatch(username):
            raise AccountError("Username: 3 to 32 characters, lowercase letters, digits, '.', '_' or '-'.")
        if not isinstance(display_name, str) or not 2 <= len(display_name.strip()) <= 100:
            raise AccountError('The display name must contain between 2 and 100 characters.')
        if role not in ROLES:
            raise AccountError('Unknown role.')
        if role == 'ADMIN':
            organisation = None
        elif not isinstance(organisation, str) or not ORGANISATION.fullmatch(organisation):
            raise AccountError('Choose an organisation.')
        pending = request_note is not None
        if pending and (role == 'ADMIN' or not isinstance(request_note, str) or not 5 <= len(request_note.strip()) <= 300):
            raise AccountError('Give your department and job title (5 to 300 characters).')
        check_password(password)
        salt = secrets.token_bytes(16)
        with self.lock:
            accounts = self._load()
            if username in accounts:
                raise AccountError('This username already exists.')
            if pending and sum(r.get('pending', False) for r in accounts.values()) >= 20:
                raise AccountError("Too many pending requests. Contact the administrator.")
            accounts[username] = {'display_name': display_name.strip(), 'role': role, 'organisation': organisation,
                                  'active': not pending, 'salt': salt.hex(), 'hash': _hash(password, salt)}
            if pending:
                accounts[username].update(pending=True, request_note=request_note.strip())
            self._save(accounts)
        return self.public(username, accounts[username])

    def update(self, username, active=None, password=None):
        if password is not None:
            check_password(password)
        with self.lock:
            accounts = self._load()
            record = accounts.get(username)
            if record is None:
                raise AccountError('Account not found.')
            if active is not None:
                if not active and record['role'] == 'ADMIN' and sum(
                        r['role'] == 'ADMIN' and r['active'] for r in accounts.values()) == 1:
                    raise AccountError('The last active administrator cannot be disabled.')
                record['active'] = bool(active)
                if active:
                    record.pop('pending', None)  # approving a request
            if password is not None:
                salt = secrets.token_bytes(16)
                record.update(salt=salt.hex(), hash=_hash(password, salt))
            self._save(accounts)
        return self.public(username, record)

    def refuse(self, username):
        with self.lock:
            accounts = self._load()
            if not accounts.get(username, {}).get('pending'):
                raise AccountError('No pending request for this account.')
            del accounts[username]
            self._save(accounts)

    def verify(self, username, password):
        """Account for a correct password, active or not; the caller refuses inactive ones."""
        record = self._load().get(username) if isinstance(username, str) else None
        if not isinstance(password, str) or len(password) > 200:
            password = ''
        if record is None:
            hmac.compare_digest(_hash(password, self.dummy[0]), self.dummy[1])
            return None
        if not hmac.compare_digest(_hash(password, bytes.fromhex(record['salt'])), record['hash']):
            return None
        return self.public(username, record)

    def get(self, username):
        record = self._load().get(username)
        return self.public(username, record) if record else None
