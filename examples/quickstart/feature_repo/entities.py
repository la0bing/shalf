from shalf.data import Entity, ValueType

customer = Entity(name="customer", join_key="customer_id", value_type=ValueType.INT64)
merchant = Entity(name="merchant", join_key="merchant_id", value_type=ValueType.INT64)
