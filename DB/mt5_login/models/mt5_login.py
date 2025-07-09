from sqlmodel import Field, SQLModel


class Mt5Login(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str | None = Field(default=None)
    password: str | None = Field(default=None)
    server: str | None = Field(default=None)
    program_path: str | None = Field(default=None)
