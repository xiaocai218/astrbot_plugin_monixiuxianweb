# data/__init__.py

from .data_manager import DataBase

__all__ = ["DataBase", "MigrationManager"]


def __getattr__(name):
    """按需导入迁移管理器，避免 config_manager -> data.default_configs 时触发循环导入。"""
    if name == "MigrationManager":
        from .migration import MigrationManager

        return MigrationManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
