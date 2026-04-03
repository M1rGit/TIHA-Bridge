import sys
from core.adapter_config import is_enabled, set_enabled, all_states
from db.database import init as db_init
from db import database as db

PLATFORMS = ("max", "telegram", "discord")


# ── Адаптеры ────────────────────────────────────────────────────────────────

def cmd_status() -> None:
    states = all_states()
    print("Состояние адаптеров:")
    for p in PLATFORMS:
        icon = "✅" if states.get(p, True) else "❌"
        print(f"  {icon}  {p}")


def cmd_enable(platform: str) -> None:
    _check_platform(platform)
    set_enabled(platform, True)
    print(f"✅ {platform} включён")


def cmd_disable(platform: str) -> None:
    _check_platform(platform)
    set_enabled(platform, False)
    print(f"❌ {platform} выключен")


def cmd_toggle(platform: str) -> None:
    _check_platform(platform)
    current = is_enabled(platform)
    set_enabled(platform, not current)
    print(f"🔄 {platform} теперь {'включён' if not current else 'выключен'}")


# ── Маршруты ────────────────────────────────────────────────────────────────

def cmd_route(args: list[str]) -> None:
    if not args:
        _route_usage()
        return

    sub = args[0]

    match sub:
        case "list":
            rows = db.get_all_routes()
            if not rows:
                print("Маршрутов нет.")
                return
            print(f"{'ID':<4}  {'Источник':<30}  {'Получатель':<30}")
            print("─" * 68)
            for r in rows:
                src = f"{r['source_platform']}/{r['source_title'] or r['source_chat_id']}"
                snk = f"{r['sink_platform']}/{r['sink_title'] or r['sink_chat_id']}"
                print(f"{r['id']:<4}  {src:<30}  {snk:<30}")

        case "add":
            if len(args) != 5:
                print("Использование: route add <src_platform> <src_chat_id> <sink_platform> <sink_chat_id>")
                sys.exit(1)
            _, src_plat, src_chat, snk_plat, snk_chat = args
            _check_platform(src_plat)
            _check_platform(snk_plat)
            db.add_route(src_plat, src_chat, snk_plat, snk_chat)
            print(f"✅ Маршрут добавлен: {src_plat}/{src_chat} → {snk_plat}/{snk_chat}")

        case "remove":
            if len(args) != 2:
                print("Использование: route remove <route_id>")
                sys.exit(1)
            try:
                route_id = int(args[1])
            except ValueError:
                print("route_id должен быть числом.")
                sys.exit(1)
            db.remove_route(route_id)
            print(f"✅ Маршрут #{route_id} удалён.")

        case _:
            _route_usage()


def _route_usage() -> None:
    print("Использование:")
    print("  route list")
    print("  route add <src_platform> <src_chat_id> <sink_platform> <sink_chat_id>")
    print("  route remove <route_id>")


# ── Админы ───────────────────────────────────────────────────────────────────

def cmd_admin(args: list[str]) -> None:
    if not args:
        _admin_usage()
        return

    sub = args[0]

    match sub:
        case "list":
            any_found = False
            for p in PLATFORMS:
                admins = db.get_admins(p)
                if admins:
                    any_found = True
                    print(f"{p}:")
                    for uid in admins:
                        print(f"  {uid}")
            if not any_found:
                print("Админов нет.")

        case "add":
            if len(args) != 3:
                print("Использование: admin add <platform> <user_id>")
                sys.exit(1)
            _, platform, user_id = args
            _check_platform(platform)
            db.add_admin(platform, user_id)
            print(f"✅ Админ добавлен: {platform}/{user_id}")

        case "remove":
            if len(args) != 3:
                print("Использование: admin remove <platform> <user_id>")
                sys.exit(1)
            _, platform, user_id = args
            _check_platform(platform)
            db.remove_admin(platform, user_id)
            print(f"✅ Админ удалён: {platform}/{user_id}")

        case _:
            _admin_usage()


def _admin_usage() -> None:
    print("Использование:")
    print("  admin list")
    print("  admin add <platform> <user_id>")
    print("  admin remove <platform> <user_id>")


# ── Утилиты ──────────────────────────────────────────────────────────────────

def _check_platform(platform: str) -> None:
    if platform not in PLATFORMS:
        print(f"Неизвестная платформа: '{platform}'. Доступны: {', '.join(PLATFORMS)}")
        sys.exit(1)


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    db_init()  # создаёт таблицы если БД новая

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    command = args[0]
    rest    = args[1:]

    match command:
        case "status":
            cmd_status()
        case "enable" if rest:
            cmd_enable(rest[0])
        case "disable" if rest:
            cmd_disable(rest[0])
        case "toggle" if rest:
            cmd_toggle(rest[0])
        case "route":
            cmd_route(rest)
        case "admin":
            cmd_admin(rest)
        case _:
            print(__doc__)
            sys.exit(1)


if __name__ == "__main__":
    main()
