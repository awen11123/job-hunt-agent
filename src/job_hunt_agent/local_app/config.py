import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator


class LocalAppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    excel_path: Path | None = None
    backup_dir: Path
    interview_dir: Path
    notion_enabled: bool = False
    model_enabled: bool = False

    @field_validator("excel_path", "backup_dir", "interview_dir", mode="before")
    @classmethod
    def validate_absolute_path(cls, value: object, info: ValidationInfo) -> object:
        is_blank = value is None or (isinstance(value, str) and not value.strip())
        if is_blank:
            if info.field_name == "excel_path":
                return None
            raise ValueError(f"{info.field_name} must not be empty")

        if isinstance(value, (str, Path)):
            path = Path(value)
            if not path.is_absolute():
                raise ValueError(f"{info.field_name} must be an absolute path")
            return value
        return value

    @classmethod
    def defaults(cls, app_data_root: Path) -> "LocalAppConfig":
        return cls(
            backup_dir=app_data_root / "backups",
            interview_dir=app_data_root / "interviews",
        )


class LocalConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> LocalAppConfig:
        if not self.path.exists():
            return LocalAppConfig.defaults(self.path.parent)
        return LocalAppConfig.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, config: LocalAppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        safe_config = LocalAppConfig(
            **{field_name: getattr(config, field_name) for field_name in LocalAppConfig.model_fields}
        )

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(safe_config.model_dump_json(indent=2))
                temporary.flush()
                os.fsync(temporary.fileno())

            LocalAppConfig.model_validate_json(temporary_path.read_text(encoding="utf-8"))
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
