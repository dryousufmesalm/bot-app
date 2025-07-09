from .app_router import AppRoutes

class AppState:
    login_data: dict[str, str]
    token: str = None
    local_db: bool = False
    Mt5_authorized: bool = False
    def clear():
        AppState.login_data = {}
        AppState.token = None
        AppState.local_db = None
        # Change the route to the login page
        AppRouter.change_route(AppRoutes.LOGIN)
    @staticmethod
    def set_local_db(state: bool):
        AppState.local_db = state
        
    @staticmethod
    def set_token(token: str):
        AppState.token = token
        
    @staticmethod
    def get_local_db():
        return AppState.local_db

store = AppState()