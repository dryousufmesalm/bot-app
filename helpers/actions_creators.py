from __future__ import absolute_import
from helpers.store import store
from helpers.action_types import (
    DISPATCH_IN_MIDDLE, THROW_ERROR, UNKNOWN_ACTION, ADD_ACCOUNT, ADD_USER, ADD_MT5
)


def add_user(user_data, auth_api, username, password):
    return {
        'type': ADD_USER,
        'payload': {
            'user_data': user_data,
            'auth': auth_api,
            'username': username,
            'password': password,

        }


    }


def add_mt5(user, account, mt5):
    return {
        'type': ADD_MT5,
        'payload': {
            'user': user,
            'account': account,
            'mt5': mt5
        }
    }


def add_account(user_id, account_data):
    return {
        'type': ADD_ACCOUNT,
        'payload':
        {
            'user_id': user_id,
            'account_data': account_data
        }
    }


def GetUser(user_id):
    states = store.get_state()
    for user in states['users']['users']:
        if user['id'] == user_id:
            return user


def GetAccount(user_id, account_id):
    states = store.get_state()
    for user in states['users']['users']:
        if user['id'] == user_id:
            for account in user['accounts']:
                if account.id == account_id:
                    return account


def isMt5Authorized(user_id, account_id):
    states = store.get_state()
    for user in states['users']['users']:
        if user['id'] == user_id:
            for account in user['accounts']:
                if account.id == account_id:
                    meta_trader = account.mt5
                    if meta_trader is None:
                        return False
                    if meta_trader.authorized is True:
                        return True
    return False


def dispatch_in_middle(bound_dispatch_fn):
    return {
        'type': DISPATCH_IN_MIDDLE,
        'bound_dispatch_fn': bound_dispatch_fn,
    }


def throw_error():
    return {
        'type': THROW_ERROR,
    }


def unknown_action():
    return {
        'type': UNKNOWN_ACTION,
    }
