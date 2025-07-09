import flet
from helpers.store import store
from helpers.actions_creators import GetUser, add_account
from Views.globals.app_router import AppRoutes
from fletx import Xview


class AccountPageView(Xview):
    def build(self):
        user_id = self.get_param('user')
        user_data = GetUser(user_id)
        if not user_data:
            self.back()
        auth = user_data.get('auth_api')
        accounts = auth.get_accounts(user_id)
        for account in accounts:
            store.dispatch(add_account(user_id, account))
        headline = flet.Text(
            value=user_data.get('name') + " Accounts",
            style=flet.TextStyle(
                size=28,
                weight=flet.FontWeight.BOLD,
                color=flet.Colors.PRIMARY,
            ),
            text_align=flet.TextAlign.CENTER,
        )

        # states = store.get_state()
        # users = states['users']['users']
        accounts_buttons = []
        for account in accounts:
            accounts_buttons.append(
                flet.ElevatedButton(
                    text=account.name,
                    expand=False,
                    width=300,
                    on_click=lambda e, account=account: self.go(
                        f'/bots/{user_id}/{account.id}'),
                )
            )
        back_button = flet.Button(
            text="< back",
            on_click=lambda e: self.back(),
            expand=False,
            width=200,
            color=flet.Colors.TERTIARY,
        )
    
        return flet.View(
            horizontal_alignment=flet.CrossAxisAlignment.CENTER,
            vertical_alignment=flet.MainAxisAlignment.CENTER,
            controls=[
                headline,
                *accounts_buttons,
                back_button,
            ]

        )
