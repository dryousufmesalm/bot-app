from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError
from DB.ah_strategy.models.ah_cycles import AHCycle
from DB.ah_strategy.models.ah_cycles_orders import AhCyclesOrders
from datetime import datetime
from sqlalchemy import and_


class AHRepo:
    def __init__(self, engine):
        self.engine = engine

    def get_cycle(self) -> AHCycle | None:
        with Session(self.engine) as session:
            result = session.get(AHCycle, 1)
            return result

    def get_cycle_by_id(self, id) -> AHCycle | None:
        with Session(self.engine) as session:
            result = session.get(AHCycle, id)
            return result

    def get_cycle_by_remote_id(self, cycle_id) -> AHCycle | None:
        with Session(self.engine) as session:
            result = session.exec(select(AHCycle).where(
                AHCycle.id == cycle_id)).first()
            return result

    def get_active_cycles(self, bot) -> list[AHCycle] | None:
        """
        Retrieve all active cycles for a given account.

        :param account: The account to filter active cycles.
        :return: A list of active AHCycle objects or None.
        """
        with Session(self.engine) as session:
            cycles = session.exec(select(AHCycle).where(
                AHCycle.is_closed == False and AHCycle.bot == bot
            )).all()

            active_cycles = [cycle for cycle in cycles if cycle.bot == bot]
            return active_cycles

    def get_all_cycles(self) -> list[AHCycle] | None:
        with Session(self.engine) as session:
            result = session.exec(select(AHCycle)).all()
            return result

    def create_cycle(self, cycle_data) -> AHCycle | None:
        try:
            with Session(self.engine) as session:
                new_cycle = AHCycle(**cycle_data)
                session.add(new_cycle)
                session.commit()
                session.refresh(new_cycle)
                return new_cycle
        except SQLAlchemyError as e:
            print(f"Failed to create AH cycle: {e}")
            return None

    def Update_cycle(self, id, cycle_data) -> AHCycle | None:
        try:
            with Session(self.engine) as session:
                cycle = session.get(AHCycle,    id)
                if cycle:
                    for key, value in cycle_data.items():
                        setattr(cycle, key, value)
                    session.add(cycle)
                    session.commit()
                    session.refresh(cycle)
                    return cycle
                return None
        except SQLAlchemyError as e:
            print(f"Failed to update AH cycle: {e}")
            return None

    def update_cycle_by_remote_id(self, cycle_id, cycle_data) -> AHCycle | None:
        try:
            with Session(self.engine) as session:
                cycle = self.get_cycle_by_remote_id(cycle_id)
                if cycle:
                    for key, value in cycle_data.items():
                        setattr(cycle, key, value)
                    session.add(cycle)
                    session.commit()
                    session.refresh(cycle)
                    return cycle
                return None
        except SQLAlchemyError as e:
            print(f"Failed to update AH cycle: {e}")
            return None

    def close_cycle(self, cycle_id) -> AHCycle | None:
        try:
            with Session(self.engine) as session:
                cycle = session.get(AHCycle, cycle_id)
                if cycle:
                    cycle.is_closed = True
                    session.add(cycle)
                    session.commit()
                    session.refresh(cycle)
                    return cycle
                return None
        except SQLAlchemyError as e:
            print(f"Failed to close AH cycle: {e}")
            return None

    def create_order(self, order_data) -> AhCyclesOrders | None:
        try:
            with Session(self.engine) as session:
                new_order = AhCyclesOrders(**order_data)
                session.add(new_order)
                session.commit()
                session.refresh(new_order)
                return new_order
        except SQLAlchemyError as e:
            print(f"Failed to create AH order: {e}")
            return None

    def close_order(self, order_id) -> AhCyclesOrders | None:
        try:
            with Session(self.engine) as session:
                order = session.get(AhCyclesOrders, order_id)
                if order:
                    order.is_closed = True
                    session.add(order)
                    session.commit()
                    session.refresh(order)
                    return order
                return None
        except SQLAlchemyError as e:
            print(f"Failed to close AH order: {e}")
            return None

    def get_order_by_ticket(self, ticket) -> AhCyclesOrders | None:
        with Session(self.engine) as session:
            result = session.exec(select(AhCyclesOrders).where(
                AhCyclesOrders.ticket == ticket)).first()
            return result

    def get_order_by_id(self, id) -> list[AhCyclesOrders] | None:
        with Session(self.engine) as session:
            result = session.get(AhCyclesOrders, id)
            return result

    def get_orders_by_cycle_id(self, cycle_id) -> list[AhCyclesOrders] | None:
        with Session(self.engine) as session:
            result = session.exec(select(AhCyclesOrders).where(
                AhCyclesOrders.cycle_id == cycle_id)).all()
            return result

    def get_open_pending_orders(self) -> list[AhCyclesOrders] | None:
        with Session(self.engine) as session:
            result = session.exec(select(AhCyclesOrders).where(
                AhCyclesOrders.is_closed == False and AhCyclesOrders.is_pending == True)).all()
            return result

    def get_all_orders(self) -> list[AhCyclesOrders] | None:
        with Session(self.engine) as session:
            result = session.exec(select(AhCyclesOrders)).all()
            return result

    def get_open_orders_only(self) -> list[AhCyclesOrders] | None:
        with Session(self.engine) as session:
            result = session.exec(select(AhCyclesOrders).where(
                AhCyclesOrders.is_closed == False)).all()
            return result

    def update_order_by_ticket(self, ticket, order_data) -> AhCyclesOrders | None:
        try:
            with Session(self.engine) as session:
                order = self.get_order_by_ticket(ticket)
                if order:
                    for key, value in order_data.items():
                        setattr(order, key, value)
                    session.add(order)
                    session.commit()
                    session.refresh(order)
                    return order
                return None
        except SQLAlchemyError as e:
            print(f"Failed to update AH order: {e}")
            return None

    def update_order_by_id(self, id, order_data) -> AhCyclesOrders | None:
        try:
            with Session(self.engine) as session:
                order = session.get(AhCyclesOrders, id)
                if order:
                    for key, value in order_data.items():
                        setattr(order, key, value)
                    session.add(order)
                    session.commit()
                    session.refresh(order)
                    return order
                return None
        except SQLAlchemyError as e:
            print(f"Failed to update AH order: {e}")
            return None

    def get_recently_closed_cycles(self, account_id, timestamp):
        """
        Get cycles that were recently closed after the specified timestamp.
        Used to check for cycles that might have been incorrectly marked as closed.

        Args:
            account_id: The account ID to filter by
            timestamp: Unix timestamp to filter by (get cycles closed after this time)

        Returns:
            List of cycles
        """
        with Session(self.engine) as session:
            statement = select(AHCycle).where(
                and_(
                    AHCycle.account == account_id,
                    AHCycle.is_closed == True,
                    # If we had a closed_at timestamp field, we would use it here
                    # For now, just get all closed cycles
                )
            )
            cycles = session.exec(statement).all()
            return cycles
