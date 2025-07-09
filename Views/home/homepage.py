import flet
from helpers.store import store
from Views.globals.app_router import AppRoutes
from fletx import Xview


class HomePageView(Xview):
    def build(self):

        # You can use subscribe() to update the UI in response to state changes

        headline = flet.Text(
            value="Patrick Display",
            style=flet.TextStyle(
                size=28,
                weight=flet.FontWeight.BOLD,
                color=flet.Colors.PRIMARY,
            ),
            text_align=flet.TextAlign.CENTER,
        )
        add_account_button = flet.ElevatedButton(
            text="Add User",
            expand=False,
            on_click=lambda e: self.go(AppRoutes.LOGIN_PB),
            width=300,
        )

        states = store.get_state()
        users = states['users']['users']
        user_buttons = flet.ListView(spacing=10)

        for user in users:
            user_buttons.controls.append(
                flet.Row(
                    controls=[
                        flet.ElevatedButton(
                            text=user['name'],
                            expand=False,
                            width=300,
                            on_click=lambda e, user=user: self.go(
                                f'/accounts/{user["id"]}'),
                        )
                    ],
                    alignment=flet.MainAxisAlignment.CENTER,
                    spacing=10
                )
            )

        def on_state_change():
            state = store.get_state()

            users = state['users']['users']
            user_buttons.controls.clear()  # Clear existing buttons before adding new ones
            for user in users:
                user_buttons.controls.append(
                    flet.Row(
                        controls=[
                            flet.ElevatedButton(
                                text=user['name'],
                                expand=False,
                                width=300,
                                on_click=lambda e, user=user: self.go(
                                    f'/accounts/{user["id"]}'),
                            )
                        ],
                        alignment=flet.MainAxisAlignment.CENTER,

                    )
                )

            self.page.update()
            # self.page.run_task(lambda: _update_ui(state))
        store.subscribe(on_state_change)

        users_headline = flet.Text(
            value="Users",
            style=flet.TextStyle(
                size=18,
                weight=flet.FontWeight.BOLD,
                color=flet.Colors.PRIMARY,
            ),
            text_align=flet.TextAlign.CENTER,
        )

        return flet.View(
            horizontal_alignment=flet.CrossAxisAlignment.CENTER,
            vertical_alignment=flet.MainAxisAlignment.CENTER,
            controls=[
                headline,
                add_account_button,
                users_headline,
                user_buttons,
            ]

        )
