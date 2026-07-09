"""
manage_users.py
----------------
Create, reset, or remove chatbot login accounts. There is NO public
self-registration endpoint by design (see app/core/auth.py) - accounts are
created here, by whoever administers the deployment.

Usage (from the project root, with the venv active):
    python -m scripts.manage_users create <username> <password> [display_name]
    python -m scripts.manage_users reset-password <username> <new_password>
    python -m scripts.manage_users delete <username>
    python -m scripts.manage_users list
"""

import sys

from app.core import auth
from app.core.redis_client import get_redis


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "create":
        if len(sys.argv) < 4:
            print("Usage: python -m scripts.manage_users create <username> <password> [display_name]")
            sys.exit(1)
        username, password = sys.argv[2], sys.argv[3]
        display_name = sys.argv[4] if len(sys.argv) > 4 else username
        try:
            auth.create_user(username, password, display_name)
            print(f"Created user '{username}' ({display_name}).")
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)

    elif cmd == "reset-password":
        if len(sys.argv) < 4:
            print("Usage: python -m scripts.manage_users reset-password <username> <new_password>")
            sys.exit(1)
        username, new_password = sys.argv[2], sys.argv[3]
        try:
            auth.set_password(username, new_password)
            print(f"Password reset for '{username}'.")
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)

    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: python -m scripts.manage_users delete <username>")
            sys.exit(1)
        auth.delete_user(sys.argv[2])
        print(f"Deleted user '{sys.argv[2]}' (if it existed).")

    elif cmd == "list":
        r = get_redis()
        keys = r.keys("auth:user:*")
        if not keys:
            print("No users yet.")
        for key in keys:
            username = key.split("auth:user:", 1)[1]
            info = r.hgetall(key)
            print(f"  {username}  ({info.get('display_name', username)})")

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
