from sqlalchemy import select
from sqlalchemy.orm import Session

from database_ops.models import Customer


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        customer_id: str,
        customer_name: str,
        email: str | None = None,
        address: str | None = None,
        phone_number: str | None = None,
    ) -> Customer:
        customer = Customer(
            id=customer_id,
            name=customer_name,
            email=email,
            address=address,
            phone_number=phone_number,
        )

        self.db.add(customer)
        self.db.flush()  # Writes to DB but doesn't commit

        return customer

    def get_by_id(
        self,
        customer_id: str,
        lock_for_update: bool = False,
    ) -> Customer | None:

        stmt = select(Customer).where(Customer.id == customer_id)

        if lock_for_update:
            stmt = stmt.with_for_update()

        return self.db.execute(stmt).scalar_one_or_none()

    def get_all(self) -> list[Customer]:
        stmt = select(Customer)
        return list(self.db.execute(stmt).scalars().all())

    def update(
        self,
        customer: Customer,
        *,
        name: str | None = None,
        email: str | None = None,
        address: str | None = None,
        phone_number: str | None = None,
    ) -> Customer:

        if name is not None:
            customer.name = name

        if email is not None:
            customer.email = email

        if address is not None:
            customer.address = address

        if phone_number is not None:
            customer.phone_number = phone_number

        self.db.flush()

        return customer

    def delete(self, customer: Customer) -> None:
        self.db.delete(customer)
        self.db.flush()
