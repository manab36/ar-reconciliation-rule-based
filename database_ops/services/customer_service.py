from sqlalchemy.orm import Session

from database_ops.models import Customer
from database_ops.repositories.customer_repository import CustomerRepository


class CustomerService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CustomerRepository(db)

    def create_customer(
        self,
        customer_id: str,
        customer_name: str,
        email: str | None = None,
        address: str | None = None,
        phone_number: str | None = None,
    ) -> Customer:
        """Create a new customer."""
        return self.repo.create(
            customer_id=customer_id,
            customer_name=customer_name,
            email=email,
            address=address,
            phone_number=phone_number,
        )

    def update_customer_name(
        self,
        customer_id: str,
        new_name: str,
    ) -> Customer:
        customer = self.repo.get_by_id(
            customer_id,
            lock_for_update=True,
        )

        if not customer:
            raise ValueError("Customer not found")

        self.repo.update(
            customer,
            name=new_name,
        )

        return customer

    def customer_exists(self, customer_id: str) -> bool:
        """Check if a customer exists for the given customer_id. Returns True if exists, else False."""
        customer = self.repo.get_by_id(customer_id)
        return customer is not None
