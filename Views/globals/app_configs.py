from pydantic_settings import BaseSettings


class AppConfigs(BaseSettings):
    # App configs
    app_name: str = "Patrick App"
    app_version: str = "1.0.0"
    # Pocketbase configs
    pb_url: str = "https://pdapp.fppatrading.com"  # the pocketbase url
    auth_collection: str = "users"  # the collection to authenticate with, ex: 'users'
