import queue
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Account:
    """Account information with usage tracking"""

    access_key: str
    secret_key: str
    quota: int = 1000

    def has_quota(self) -> bool:
        return self.quota >= 3

    def update_remaining_quota(self, new_quota) -> None:
        self.quota = new_quota

    def remaining_quota(self) -> int:
        return self.quota


class AccountQueue:
    """Thread-safe queue for managing accounts"""

    def __init__(self, accounts: List[Tuple[str, str]]):
        self.queue = queue.Queue()
        self.lock = threading.Lock()
        self.all_accounts = []

        for access_key, secret_key in accounts:
            account = Account(access_key, secret_key)
            self.all_accounts.append(account)
            self.queue.put(account)

    def get_account(self, timeout: float = 1.0) -> Optional[Account]:
        """Get an account from the queue"""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def return_account(self, account: Account):
        """Return an account to the queue if it has quota left"""
        if account.has_quota():
            self.queue.put(account)

    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return self.queue.empty()
