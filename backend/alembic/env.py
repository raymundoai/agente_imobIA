from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config import get_settings
from app.modules.ai.adapters import models as ai_models  # noqa: F401
from app.modules.billing_usage.adapters import models as usage_models  # noqa: F401
from app.modules.capture import models as capture_models  # noqa: F401
from app.modules.contacts import models as contact_models  # noqa: F401
from app.modules.conversations.adapters import models as conversation_models  # noqa: F401
from app.modules.leads.adapters import models as lead_models  # noqa: F401
from app.modules.maintenance.adapters import models as maintenance_models  # noqa: F401
from app.modules.messaging import models as messaging_models  # noqa: F401
from app.modules.platform import models as platform_models  # noqa: F401
from app.modules.properties.adapters import models as property_models  # noqa: F401
from app.modules.tenants.adapters import models as tenant_models  # noqa: F401
from app.modules.users.adapters import models as user_models  # noqa: F401
from app.shared.database.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
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
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
