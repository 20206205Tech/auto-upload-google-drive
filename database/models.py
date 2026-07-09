from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Hướng dẫn từ DBML tạo cho database
# # Table users {
# #   userId uuid [pk, default: `uuid_generate_v4()`]
# #   email varchar [unique, not null]
# #   created_at timestamp [default: `now()`]
# # }
