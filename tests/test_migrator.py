from __future__ import annotations

import pytest
from typing import TYPE_CHECKING
import peewee as pw

if TYPE_CHECKING:
    from peewee_migrate import Migrator


def test_migrator(router):
    from peewee_migrate import Migrator

    migrator = Migrator(router.database)

    @migrator.create_table
    class Customer(pw.Model):
        name = pw.CharField()

    assert Customer == migrator.orm["customer"]

    @migrator.create_table
    class Order(pw.Model):
        number = pw.CharField()
        uid = pw.CharField(unique=True)

        customer_id = pw.ForeignKeyField(Customer, column_name="customer_id")

    assert Order == migrator.orm["order"]
    meta = Order._meta  # type: ignore[]
    migrator()

    migrator.add_columns(Order, finished=pw.BooleanField(default=False))
    assert "finished" in meta.fields
    migrator()

    migrator.drop_columns("order", "finished", "customer_id", "uid")
    assert "finished" not in meta.fields
    assert not hasattr(Order, "customer_id")
    assert not hasattr(Order, "customer_id_id")
    migrator()

    migrator.add_columns(Order, customer=pw.ForeignKeyField(Customer, null=True))
    assert "customer" in meta.fields
    assert Order.customer.name == "customer"  # type: ignore[]
    migrator()
    assert Order.customer.name == "customer"  # type: ignore[]

    migrator.rename_column(Order, "number", "identifier")
    assert "identifier" in meta.fields
    migrator()

    migrator.drop_not_null(Order, "identifier")
    assert meta.fields["identifier"].null
    assert meta.columns["identifier"].null
    migrator()

    migrator.add_default(Order, "identifier", 11)
    assert meta.fields["identifier"].default == 11
    migrator()

    migrator.change_columns(Order, identifier=pw.IntegerField(default=0))
    assert Order.identifier.field_type == "INT"  # type: ignore[]
    migrator()

    Order.create(identifier=55)
    migrator.sql('UPDATE "order" SET identifier = 77;')
    migrator()
    order = Order.get()
    assert order.identifier == 77

    migrator.add_index(Order, "identifier", "customer")
    migrator()
    assert meta.indexes
    assert not Order.identifier.index  # type: ignore[]

    migrator.drop_index(Order, "identifier", "customer")
    migrator()
    assert not meta.indexes

    migrator.remove_fields(Order, "customer")
    migrator()
    assert not hasattr(Order, "customer")

    migrator.add_index(Order, "identifier", unique=True)
    migrator()
    assert not Order.identifier.index  # type: ignore[]
    assert Order.identifier.unique  # type: ignore[]
    assert meta.indexes

    migrator.rename_table(Order, "orders")
    assert migrator.orm["orders"]
    assert migrator.orm["orders"]._meta.table_name == "orders"  # type: ignore[]
    migrator()

    migrator.change_columns(Order, identifier=pw.IntegerField(default=0))
    assert not Order._meta.indexes  # type: ignore[]


def test_migrator_postgres():
    """
    Ensure change_fields generates queries and
    does not cause exception
    """
    import peewee as pw

    # Monkey patch psycopg2 connect
    import psycopg2
    from playhouse.db_url import connect

    from peewee_migrate import Migrator

    from .mocks import postgres

    psycopg2.connect = postgres.MockConnection

    database = connect("postgres:///fake")

    migrator = Migrator(database)

    @migrator.create_table
    class User(pw.Model):
        name = pw.CharField()
        created_at = pw.DateField()

    assert User == migrator.orm["user"]

    # Date -> DateTime
    migrator.change_fields("user", created_at=pw.DateTimeField())
    migrator()
    assert (
        'ALTER TABLE "user" ALTER COLUMN "created_at" TYPE TIMESTAMP' in database.cursor().queries
    )

    # Char -> Text
    migrator.change_fields("user", name=pw.TextField())
    migrator()
    assert 'ALTER TABLE "user" ALTER COLUMN "name" TYPE TEXT' in database.cursor().queries


def test_rename_column(migrator: Migrator):
    Order = migrator.orm["order"]
    migrator.rename_column("order", "customer", "user")
    meta = Order._meta  # type: ignore[]
    assert meta.columns["user_id"]
    assert meta.fields["user"]
    [operation] = migrator.__ops__
    assert operation.args == ("order", "customer_id", "user_id")  # type: ignore[union-attr]

    # Rollback
    migrator()
    migrator.rename_column("order", "user", "customer")
    [operation] = migrator.__ops__
    assert operation.args == ("order", "user_id", "customer_id")  # type: ignore[union-attr]


def test_rename_table(migrator: Migrator):
    from .conftest import Customer

    migrator.rename_table("customer", "user")
    [operation] = migrator.__ops__
    assert operation.args == ("customer", "user")  # type: ignore[union-attr]

    class User(pw.Model):
        name = pw.CharField()
        age = pw.IntegerField()

    from peewee_migrate.auto import diff_many

    migrations = diff_many([migrator.orm["user"]], [User], migrator)
    assert not migrations


def test_change_field(migrator: Migrator):
    class TestTable(pw.Model):
        class Meta:
            table_name = "test_table"

        field_with_check = pw.CharField(
            null=False, constraints=[pw.Check("field_with_check in ('opt1', 'opt2')")]
        )

    migrator.create_table(TestTable)
    migrator()

    tt = migrator.orm["test_table"]
    migrator.change_fields(
        tt,
        field_with_check=pw.CharField(
            null=False,
            constraints=[pw.Check("field_with_check in ('opt1', 'opt2', 'opt3')")],
        ),
    )
    migrator()
    tt.insert(field_with_check="opt3").execute()
    with pytest.raises(pw.IntegrityError):
        tt.insert(field_with_check="opt4").execute()
