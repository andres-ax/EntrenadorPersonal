"""Bootstrap del primer admin del panel.

Uso:
    python scripts/crear_admin.py --email entrenadorax@axsoftware.codes --password "secreta-larga" --rol super
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from src.api.admin_auth import hash_password  # noqa: E402
from src.db.connection import async_session_factory  # noqa: E402
from src.db.models import Admin, RolAdmin  # noqa: E402


async def crear(email: str, password: str, rol: str) -> None:
    try:
        rol_enum = RolAdmin(rol)
    except ValueError:
        sys.stderr.write(f"rol invalido: {rol}. Use 'super' o 'soporte'\n")
        sys.exit(1)
    async with async_session_factory() as session:
        existente = await session.execute(select(Admin).where(Admin.email == email.lower()))
        if existente.scalar_one_or_none() is not None:
            sys.stderr.write(f"Admin con email {email} ya existe\n")
            sys.exit(1)
        nuevo = Admin(
            email=email.lower(),
            password_hash=hash_password(password),
            rol=rol_enum,
            activo=True,
        )
        session.add(nuevo)
        await session.commit()
        sys.stdout.write(f"Admin creado: id={nuevo.id} email={nuevo.email} rol={nuevo.rol.value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--rol", default="super", choices=["super", "soporte"])
    args = parser.parse_args()
    asyncio.run(crear(args.email, args.password, args.rol))


if __name__ == "__main__":
    main()
