from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from database_ops.model import Customer


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_customer(self, id: str, name: str, email: str = None, address: str = None, phone_number: str = None) -> Customer:
        customer = Customer(id=id, name=name, email=email, address=address, phone_number=phone_number)
        self.db.add(customer)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        self.db.refresh(customer)
        return customer

    def get_customer_by_id(self, customer_id: str) -> Customer | None:
        return self.db.query(Customer).filter_by(id=customer_id).first()

    def get_all_customers(self) -> list[Customer]:
        return self.db.query(Customer).all()

    def update_customer(self, customer_id: str, name: str = None, email: str = None, address: str = None, phone_number: str = None) -> Customer | None:
        customer = self.get_customer_by_id(customer_id)
        if not customer:
            return None
        if name is not None:
            customer.name = name
        if email is not None:
            customer.email = email
        if address is not None:
            customer.address = address
        if phone_number is not None:
            customer.phone_number = phone_number
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def delete_customer(self, customer_id: str) -> bool:
        customer = self.get_customer_by_id(customer_id)
        if not customer:
            return False
        self.db.delete(customer)
        self.db.commit()
        return True
