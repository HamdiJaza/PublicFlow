"""Citizen accounts keyed by the national ID card number (CIN), stored in .runtime/portal.

The CIN is never stored in clear: accounts are indexed by an HMAC of the CIN with a local
key, and only its last two digits are kept for display. Passwords are scrypt hashes.
Tickets, n8n and the database never receive the CIN or the account.
"""
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import threading

# Demo rule requested for the project: exactly 8 digits, the first one is 0.
CIN = re.compile(r'0[0-9]{7}')
MAX_REPORTS = 200


class CitizenError(ValueError):
    """Message is safe to show to the citizen."""


def _hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, maxmem=64 * 1024 * 1024).hex()


def check_cin(cin):
    if not isinstance(cin, str) or not CIN.fullmatch(cin):
        raise CitizenError('The CIN must contain exactly 8 digits and start with 0.')


class Citizens:
    def __init__(self, directory):
        directory = Path(directory)
        self.path = directory / 'citizens.json'
        self.key_path = directory / 'cin-key.txt'
        self.lock = threading.Lock()
        self.dummy = (secrets.token_bytes(16), _hash(secrets.token_urlsafe(16), b'0' * 16))

    def _key(self):
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.key_path.exists():
            try:
                with self.key_path.open('x', encoding='ascii') as stream:
                    stream.write(secrets.token_hex(32))
            except FileExistsError:
                pass
        return bytes.fromhex(self.key_path.read_text(encoding='ascii').strip())

    def account_id(self, cin):
        return hmac.new(self._key(), cin.encode('ascii'), hashlib.sha256).hexdigest()

    def _load(self):
        if not self.path.is_file():
            return {}
        data = json.loads(self.path.read_text(encoding='utf-8'))
        return data['citizens'] if data.get('format') == 2 else {}

    def _save(self, citizens):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps({'format': 2, 'citizens': citizens}, indent=2), encoding='utf-8')
        tmp.replace(self.path)

    @staticmethod
    def public(account_id, record):
        return {'account': account_id, 'cin_hint': record['cin_last2']}

    def create(self, cin, password):
        check_cin(cin)
        if not isinstance(password, str) or not 8 <= len(password) <= 200:
            raise CitizenError('The password must contain between 8 and 200 characters.')
        account_id, salt = self.account_id(cin), secrets.token_bytes(16)
        with self.lock:
            citizens = self._load()
            if account_id in citizens:
                raise CitizenError('An account already exists for this CIN. Sign in instead.')
            citizens[account_id] = {'cin_last2': cin[-2:], 'salt': salt.hex(), 'hash': _hash(password, salt), 'reports': []}
            self._save(citizens)
        return self.public(account_id, citizens[account_id])

    def verify(self, cin, password):
        password = password if isinstance(password, str) and len(password) <= 200 else ''
        record = None
        if isinstance(cin, str) and CIN.fullmatch(cin):
            account_id = self.account_id(cin)
            record = self._load().get(account_id)
        if record is None:
            hmac.compare_digest(_hash(password, self.dummy[0]), self.dummy[1])
            return None
        if not hmac.compare_digest(_hash(password, bytes.fromhex(record['salt'])), record['hash']):
            return None
        return self.public(account_id, record)

    def get(self, account_id):
        record = self._load().get(account_id)
        return self.public(account_id, record) if record else None

    def add_report(self, account_id, report_id):
        with self.lock:
            citizens = self._load()
            record = citizens.get(account_id)
            if record is not None and report_id not in record['reports']:
                record['reports'] = (record['reports'] + [report_id])[-MAX_REPORTS:]
                self._save(citizens)

    def reports(self, account_id):
        return list((self._load().get(account_id) or {}).get('reports', []))
