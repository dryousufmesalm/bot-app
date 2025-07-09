from DB.db_engine import engine
from sqlmodel import Session, select

from DB.mt5_login.models.mt5_login import Mt5Login


class MT5LoginRepo:
    def __init__(self, engine):
        self.engine = engine

    def get_mt5_credentials(self, mt5_account_id) -> Mt5Login | None:
        with Session(self.engine) as session:
            # GET LAST LOGIN
            Query = select(Mt5Login).where(Mt5Login.username ==
                                           mt5_account_id).order_by(Mt5Login.id.desc()).limit(1)
            result = session.execute(Query).first()
            if result:
                mt5_login = result[0]
                print("result", mt5_login)
                return mt5_login
            return None

    def set_mt5_credentials(self, data) -> Mt5Login | None:
        """Set MT5 credentials."""
        with Session(self.engine) as session:
            mt5_login = Mt5Login(
                username=data["username"],
                password=data["password"],
                server=data["server"],
                program_path=data["program_path"]
            )
            session.add(mt5_login)
            session.commit()
            print(mt5_login.id)
            return mt5_login
