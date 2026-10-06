from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


import app.models.user  # noqa: E402, F401
import app.models.chat  # noqa: E402, F401
import app.models.research_report  # noqa: E402, F401
import app.models.generation  # noqa: E402, F401
