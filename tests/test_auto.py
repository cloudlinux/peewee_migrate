from __future__ import annotations

import datetime as dt
from pathlib import Path

import peewee as pw
from playhouse.postgres_ext import (
    ArrayField,
    BinaryJSONField,
    DateTimeTZField,
    HStoreField,
    IntervalField,
    JSONField,
    TSVectorField,
)

CURDIR = Path(__file__).parent


def test_auto():
    from peewee_migrate.auto import diff_many, diff_one, model_to_code
    from peewee_migrate.cli import get_router

    router = get_router(CURDIR / "migrations", "sqlite:///:memory:")
    router.run()
    migrator = router.migrator
    models = list(migrator)
    person_cls = migrator.orm.Person
    tag_cls = migrator.orm.Tag

    code = model_to_code(person_cls)
    assert code
    assert 'table_name = "person"' in code

    changes = diff_many(models, [], migrator=migrator)
    assert len(changes) == 2

    class Person(pw.Model):
        first_name = pw.IntegerField()
        last_name = pw.CharField(max_length=1024, null=True, unique=True)
        tag = pw.ForeignKeyField(tag_cls, on_delete="CASCADE", backref="persons")
        email = pw.CharField(index=True, unique=True)

    changes = diff_one(Person, person_cls, migrator=migrator)
    assert len(changes) == 6
    assert "on_delete='CASCADE'" in changes[0]
    assert "backref='persons'" not in changes[0]
    assert changes[-3] == "migrator.drop_not_null('person', 'last_name')"
    assert changes[-2] == "migrator.drop_index('person', 'last_name')"
    assert changes[-1] == "migrator.add_index('person', 'last_name', unique=True)"

    migrator.drop_index("person", "email")
    migrator.add_index("person", "email", unique=True)

    class Person2(pw.Model):
        first_name = pw.CharField(unique=True)
        last_name = pw.CharField(max_length=255, index=True)
        dob = pw.DateField(null=True)
        birthday = pw.DateField(default=dt.datetime.now)
        email = pw.CharField(index=True, unique=True)
        is_deleted = pw.BooleanField(default=False)

    changes = diff_one(person_cls, Person2, migrator=migrator)
    assert not changes

    class Color(pw.Model):
        id = pw.AutoField()
        name = pw.CharField(default="red")

    code = model_to_code(Color)
    assert "DEFAULT 'red'" in code


def test_auto_postgresext():
    from peewee_migrate.auto import model_to_code

    class Object(pw.Model):
        array_field = ArrayField()
        binary_json_field = BinaryJSONField()
        dattime_tz_field = DateTimeTZField()
        hstore_field = HStoreField()
        interval_field = IntervalField()
        json_field = JSONField()
        ts_vector_field = TSVectorField()

    code = model_to_code(Object)
    assert code
    assert "json_field = pw_pext.JSONField()" in code
    assert "hstore_field = pw_pext.HStoreField(index=True)" in code


def test_auto_multi_column_index():
    from peewee_migrate.auto import model_to_code

    class Object(pw.Model):
        first_name = pw.CharField()
        last_name = pw.CharField()

        class Meta:
            indexes = ((("first_name", "last_name"), True),)

    code = model_to_code(Object)
    assert code
    assert "indexes = [(('first_name', 'last_name'), True)]" in code


def test_diff_multi_column_index():
    from peewee_migrate.auto import diff_one

    class Object(pw.Model):
        first_name = pw.CharField()
        last_name = pw.CharField()

    class ObjectWithUniqueIndex(pw.Model):
        first_name = pw.CharField()
        last_name = pw.CharField()

        class Meta:
            indexes = ((("first_name", "last_name"), True),)

    class ObjectWithNonUniqueIndex(pw.Model):
        first_name = pw.CharField()
        last_name = pw.CharField()

        class Meta:
            indexes = ((("first_name", "last_name"), False),)

    changes = diff_one(ObjectWithUniqueIndex, Object)
    assert len(changes) == 1
    assert (
        changes[0]
        == "migrator.add_index('objectwithuniqueindex', 'first_name', 'last_name', unique=True)"
    )

    changes = diff_one(ObjectWithNonUniqueIndex, Object)
    assert len(changes) == 1
    assert (
        changes[0]
        == "migrator.add_index('objectwithnonuniqueindex', 'first_name', 'last_name', unique=False)"
    )

    changes = diff_one(ObjectWithNonUniqueIndex, ObjectWithUniqueIndex)
    assert len(changes) == 2
    assert (
        changes[0] == "migrator.drop_index('objectwithnonuniqueindex', 'first_name', 'last_name')"
    )
    assert (
        changes[1]
        == "migrator.add_index('objectwithnonuniqueindex', 'first_name', 'last_name', unique=False)"
    )


def test_self_referencing_foreign_key_on_model_create():
    from peewee_migrate.auto import field_to_code

    class Employee(pw.Model):
        manager = pw.ForeignKeyField("self")

    code = field_to_code(Employee.manager)
    assert "model='self'" in code


def test_self_referencing_foreign_key_on_field_added():
    from peewee_migrate.auto import diff_one

    class Employee(pw.Model):
        name = pw.CharField()

    class EmployeeNew(pw.Model):
        name = pw.CharField()
        manager = pw.ForeignKeyField("self")

    changes = diff_one(EmployeeNew, Employee)
    assert "migrator.add_fields" in changes[0]
    assert "model='self'" in changes[0]


def test_column_default():
    from peewee_migrate.auto import field_to_code

    from .models import Person

    code = field_to_code(Person.is_deleted)
    assert code == 'is_deleted = pw.BooleanField(constraints=[SQL("DEFAULT False")], default=False)'


def test_on_update_on_delete():
    from peewee_migrate.auto import field_to_code

    class Employee(pw.Model):
        manager = pw.ForeignKeyField("self", on_update="CASCADE", on_delete="CASCADE")

    code = field_to_code(Employee.manager)
    assert "on_update='CASCADE'" in code
    assert "on_delete='CASCADE'" in code


def test_custom_fields():
    from peewee_migrate.auto import compare_fields, field_to_code

    class Test(pw.Model):
        dtfield = pw.DateTimeField()
        datetime_tz_field = DateTimeTZField()

    code = field_to_code(Test.dtfield)
    assert code == "dtfield = pw.DateTimeField()"

    code = field_to_code(Test.datetime_tz_field)
    assert code == "datetime_tz_field = pw_pext.DateTimeTZField()"

    class CustomDatetimeField(pw.DateTimeField):
        pass

    class Test2(Test):
        dtfield = CustomDatetimeField()

    code = field_to_code(Test2.dtfield)
    assert code == "dtfield = pw.DateTimeField()"

    res = compare_fields(Test2.dtfield, Test.dtfield)
    assert not res
