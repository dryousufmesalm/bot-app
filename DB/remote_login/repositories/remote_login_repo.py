from DB.db_engine import engine
from sqlmodel import Session,select

from DB.remote_login.models.remote_login import RemoteLogin

class RemoteLoginRepo:
    def __init__(self, engine):
        self.engine = engine
    
    def get_pb_credintials(self) -> RemoteLogin | None:
        with Session(self.engine) as session:
            # GET LAST LOGIN
            Query = select(RemoteLogin).order_by(RemoteLogin.id.desc()).limit(1)
            result = session.execute(Query).first()
            if result:
                login = result[0]
                print("result", login)
                return login
            return None
    def get_All_users(self):
        with Session(self.engine) as session:
            result = session.exec(select(RemoteLogin)).all()
            return result
    def set_pb_credentials(self, data) -> RemoteLogin | None:
        """Set MT5 credentials."""
        with Session (self.engine) as session:
            mt5_login = RemoteLogin(
                username=data["username"],
                password=data["password"],
           
            )
            session.add(mt5_login)
            session.commit()
            print(mt5_login.id)
            return mt5_login
        
