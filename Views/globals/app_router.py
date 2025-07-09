from enum import StrEnum
import flet


class AppRoutes(StrEnum):

    LOGIN_PB = "/PB"
    ADD_ACCOUNT = "/ACCOUNT"
    HOME = "/"
    USER = "/user/:id"
    ACCOUNTS = "/accounts/:user"
    Bot = "/bot/:user/:account/:id"
    BOTS = "/bots/:user/:account"
    LOGIN_MT5 = "/MT5/:user/:account"
