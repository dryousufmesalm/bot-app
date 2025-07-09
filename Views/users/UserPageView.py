import flet
from helpers.store import store
from helpers.actions_creators import GetUser, add_account
from Views.globals.app_router import AppRoutes
from fletx import Xview


class UserPageView(Xview):
    def build(self):
        userid = self.get_param('id')
        user_data = GetUser(userid)
        if not user_data:
            self.back()
        auth = user_data.get('auth_api')
        accounts = auth.get_accounts(userid)
        store.dispatch(add_account(userid, accounts))
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
        for acc in accounts:
            accounts_buttons.append(
                flet.ElevatedButton(
                    text=acc.name,
                    expand=False,
                    width=300,
                    on_click=lambda e, acc=acc: self.go(
                        f'/user/{userid}/{acc.id}'),
                )
            )
        back_button = flet.Button(
            text="< Return to Home",
            on_click=lambda e: self.go(AppRoutes.HOME),
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
