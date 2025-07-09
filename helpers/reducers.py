from __future__ import absolute_import

from helpers.action_types import (
    ADD_USER, ADD_ACCOUNT, DISPATCH_IN_MIDDLE, THROW_ERROR, GET_USER, ADD_MT5
)


def users(state, action):
    if state is None:
        state = {
            'users': [],
        }

    if action.get('type') == ADD_USER:
        payload = action.get('payload')
        user_data = payload['user_data']
        auth = payload['auth']
        new_user = {
            'id': user_data.record.id,
            'name': user_data.record.name,
            'token': user_data.token,
            'authorized': True,
            'accounts': [],
            'auth_api': auth,
            'username': payload['username'],
            'password': payload['password'],
        }

        return {
            'users': state['users'] + [new_user],
        }

    if action.get('type') == GET_USER:
        user_id = action.get('payload')
        for user in state['users']:
            if user['id'] == user_id:
                return user
        return None
    if action.get('type') == ADD_ACCOUNT:
        payload = action.get('payload')
        account_data = payload['account_data']
        account_data.mt5 = None
        user_id = payload['user_id']
        for user in state['users']:
            if user['id'] == user_id:
                # if is already added , do nothing
                if account_data in user['accounts']:
                    return state
                # add account to user accounts list
                user['accounts'].append(account_data)
                return state
    if action.get('type') == ADD_MT5:
        payload = action.get('payload')
        mt5 = payload['mt5']
        user_id = payload['user']
        account_id = payload['account']
        for user in state['users']:
            if user['id'] == user_id:
                for account in user['accounts']:
                    if account.id == account_id:
                        account.mt5 = mt5
                        return state
    return state


def dispatch_in_middle_of_reducer(state=None, action={}):
    if state is None:
        state = []
    if action.get('type') == DISPATCH_IN_MIDDLE:
        action.get('bound_dispatch_fn')()
        return state
    else:
        return state


def error_throwing_reducer(state=None, action={}):
    if state is None:
        state = []
    if action.get('type') == THROW_ERROR:
        raise Exception()
    else:
        return state


reducers = {
    'users': users,
    'dispatch_in_middle_of_reducer': dispatch_in_middle_of_reducer,
    'error_throwing_reducer': error_throwing_reducer,
}
