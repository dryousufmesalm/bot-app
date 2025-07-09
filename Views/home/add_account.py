"""
Module for adding an account view in Patrick Display.
"""

import flet
from fletx import Xview
from Views.globals.app_router import AppRoutes
from Views.globals.app_state import store


class AddAccountView(Xview):
    def build(self):
        return flet.View(
            horizontal_alignment=flet.CrossAxisAlignment.CENTER,
            vertical_alignment=flet.MainAxisAlignment.CENTER,
            controls=[
                flet.Text(
                    value="Patrick Display",
                    style=flet.TextStyle(
                        size=28,
                        weight=flet.FontWeight.BOLD,
                        color=flet.Colors.PRIMARY,
                    ),
                    text_align=flet.TextAlign.CENTER,
                ),
                flet.ElevatedButton(
                    text="MT5 connected" if store.Mt5_authorized else "Connect MT5",
                    on_click=lambda e: self.go(AppRoutes.LOGIN_MT5),
                    expand=False,
                    width=300,
                ),

                flet.ElevatedButton(
                    text="Remote server connected" if store.token else "Login to remote server",
                    on_click=lambda e: self.go(AppRoutes.LOGIN_PB),
                    expand=False,
                    width=300,
                ),

                flet.ProgressBar(visible=False),
                flet.Button(
                    text="< Return to Home",
                    on_click=lambda e: self.go(AppRoutes.HOME),
                    expand=False,
                    width=200,
                    color=flet.Colors.TERTIARY,
                ),

            ]
        )
