import flet
import asyncio
from Views.auth import auth
from Views.globals.app_logger import app_logger
from Views.globals.app_router import AppRoutes
from DB.remote_login.repositories.remote_login_repo import RemoteLoginRepo
from DB.db_engine import engine
from fletx import Xview


class RemoteLoginPageView(Xview):

    def build(self):

        async def retuen_home(e):
            self.go(AppRoutes.HOME)
            self.update()

        async def on_login(e):
            login_progress.visible = True
            self.update()

            await asyncio.sleep(1)
            data: dict[str, any] = {
                "username":    username.value,
                "password":    password.value,
            }
            result = await auth.login(**data)
            login_progress.visible = False
            self.update()
            if result[0]:
                # TODO: navigate to the home page
                app_logger.info("Login successful, navigating to home page")
                remote_logger = RemoteLoginRepo(engine=engine)
                credentials = remote_logger.set_pb_credentials(data)
                if credentials is None:
                    app_logger.error("Failed to save credentials")
                    return
                self.back()
                if result[1]:
                    app_logger.info(msg=result[1])
            else:
                app_logger.error(msg=f"Login failed: {result[1]}")

        def load_saved_credentials():
            try:
                # Assuming `local_auth` has a method `get_credentials` returning a dict with keys 'username' and 'password'
                remote_logger = RemoteLoginRepo(engine=engine)
                credentials = remote_logger.get_pb_credintials()
                if credentials is None:
                    return None

                return credentials
            except Exception as e:
                app_logger.error(f"Failed to load saved credentials: {e}")
                return None

        credentials = load_saved_credentials()
        headline = flet.Text(
            value="Login to Patrick Server",
            style=flet.TextStyle(
                size=24,
                weight=flet.FontWeight.BOLD,
                color=flet.Colors.PRIMARY,
            ),
            text_align=flet.TextAlign.CENTER,
        )

        username = flet.TextField(label="Username", expand=False, width=500,
                                        value=credentials.username if credentials is not None else "")
        password = flet.TextField(label="Password", password=True, width=500,
                                        value=credentials.password if credentials is not None else "")
        login_button = flet.Button(
            text="Login",
            on_click=on_login,
            expand=False,
            width=200,
            color=flet.Colors.SECONDARY,
        )
        # back button
        back_button = flet.Button(
            text="< Return to Home",
            on_click=retuen_home,
            expand=False,
            width=200,
            color=flet.Colors.TERTIARY,
        )

        program_path_text = flet.Text("")
        login_progress = flet.ProgressBar(visible=False)

        return flet.View(
            horizontal_alignment=flet.CrossAxisAlignment.CENTER,
            vertical_alignment=flet.MainAxisAlignment.CENTER,
            controls=[
                headline,
                username,
                password,
                login_button,
                program_path_text,
                login_progress,
                back_button,
            ]
        )
