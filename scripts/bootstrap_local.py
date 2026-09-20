"""Create a local researcher and write credentials to an ignored environment file."""

import asyncio
import json
import os
import secrets
import shlex
from pathlib import Path

from ranah_domain.db import create_engine, create_session_factory, session_scope
from ranah_domain.models.organization import Organization, User
from sqlalchemy import select


async def main() -> None:
    target = Path(".env.discovery")
    if target.exists():
        raise SystemExit(".env.discovery already exists; source it to reuse the local identity.")
    engine = create_engine()
    async with session_scope(create_session_factory(engine)) as session:
        organization = await session.scalar(
            select(Organization).where(Organization.slug == "local")
        )
        if organization is None:
            organization = Organization(name="Local research", slug="local")
            session.add(organization)
            await session.flush()
        user = await session.scalar(
            select(User).where(User.auth_provider == "local", User.provider_subject == "researcher")
        )
        if user is None:
            user = User(
                organization_id=organization.id,
                email="researcher@localhost",
                display_name="Local researcher",
                auth_provider="local",
                provider_subject="researcher",
            )
            session.add(user)
            await session.flush()
        token = secrets.token_urlsafe(32)
        contents = f"export RANAH_API_TOKENS={shlex.quote(json.dumps({token: str(user.id)}))}\n"
        contents += f"export RANAH_LOCAL_TOKEN={shlex.quote(token)}\n"
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(contents)
    await engine.dispose()
    print("Local identity ready. Run: source .env.discovery (credentials are not printed).")


if __name__ == "__main__":
    asyncio.run(main())
