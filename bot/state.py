# bot/state.py
from bot.database import (
    save_active_slot, delete_active_slot, get_all_active_slots,
    save_slot_request, delete_slot_request, get_all_slot_requests, get_slot_request,
)


class _ActiveSlotsProxy(dict):
    def __init__(self):
        super().__init__()
        self._loaded = False

    def _load(self):
        if not self._loaded:
            for k, v in get_all_active_slots().items():
                super().__setitem__(k, v)
            self._loaded = True

    def get(self, key, default=None):
        self._load()
        return super().get(key, default)

    def __getitem__(self, key):
        self._load()
        return super().__getitem__(key)

    def __contains__(self, key):
        self._load()
        return super().__contains__(key)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        save_active_slot(key, value)

    def __delitem__(self, key):
        super().__delitem__(key)
        delete_active_slot(key)

    def items(self):
        self._load()
        return super().items()

    def keys(self):
        self._load()
        return super().keys()

    def values(self):
        self._load()
        return super().values()

    def clear(self):
        for k in list(super().keys()):
            delete_active_slot(k)
        super().clear()


class _SlotRequestsProxy(dict):
    def __init__(self):
        super().__init__()
        self._loaded = False

    def _load(self):
        if not self._loaded:
            for k, v in get_all_slot_requests().items():
                super().__setitem__(k, v)
            self._loaded = True

    def get(self, key, default=None):
        self._load()
        return super().get(key, default)

    def __getitem__(self, key):
        self._load()
        return super().__getitem__(key)

    def __contains__(self, key):
        self._load()
        return super().__contains__(key)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        save_slot_request(key, value)

    def __delitem__(self, key):
        super().__delitem__(key)
        delete_slot_request(key)

    def items(self):
        self._load()
        return super().items()

    def keys(self):
        self._load()
        return super().keys()

    def values(self):
        self._load()
        return super().values()

    def clear(self):
        for k in list(super().keys()):
            delete_slot_request(k)
        super().clear()


active_slots = _ActiveSlotsProxy()
slot_requests = _SlotRequestsProxy()
