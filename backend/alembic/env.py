from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.db import Base

# Import every models module so its tables register on Base.metadata before
# autogenerate/upgrade runs. Add new modules here as they're introduced.
from app.assistant import models as assistant_models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401
from app.briefs import models as briefs_models  # noqa: F401
from app.checkins import models as checkins_models  # noqa: F401
from app.documents import models as documents_models  # noqa: F401
from app.event_store import models as event_store_models  # noqa: F401
from app.patients import models as patients_models  # noqa: F401
from app.profile import models as profile_models  # noqa: F401
from app.rag import models as rag_models  # noqa: F401

config = context.config
# set_main_option() stores the value via ConfigParser, which treats "%" as
# interpolation syntax — a URL-encoded password (e.g. "%40" for "@") isn't
# valid interpolation syntax and raises. Escape "%" to "%%" so the URL is
# stored literally regardless of what characters the password contains.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
