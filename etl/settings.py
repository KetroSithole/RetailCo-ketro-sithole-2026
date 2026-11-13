"""Loads the settings for one environment from the .config folder.

.config/settings.env   ENVIRONMENT=dev
.config/dev.env        server, login and folders for dev
.config/prod.env       server, login and folders for prod
"""
import os
from pathlib import Path

from dotenv import dotenv_values

PROJECT_FOLDER = Path(__file__).resolve().parents[1]
CONFIG_FOLDER = PROJECT_FOLDER / ".config"


class Settings:
    def __init__(self, environment: str | None = None):
        defaultEnvironment = dotenv_values(CONFIG_FOLDER / "settings.env").get("ENVIRONMENT", "dev")
        self.environment = (environment or defaultEnvironment).lower()

        envFile = CONFIG_FOLDER / f"{self.environment}.env"
        if not envFile.exists():
            raise SystemExit(f"Missing .config/{envFile.name} - copy .config/example.env to create it.")
        values = dotenv_values(envFile)

        self.server = values["SQL_SERVER"]
        self.login = values.get("SQL_LOGIN", "windows")
        self.username = values.get("SQL_USERNAME", "")
        self.password = os.getenv("SQL_PASSWORD") or values.get("SQL_PASSWORD", "")

        self.inboxFolder = PROJECT_FOLDER / values["INBOX_FOLDER"]
        self.archiveFolder = PROJECT_FOLDER / values["ARCHIVE_FOLDER"]
        self.errorFolder = PROJECT_FOLDER / values["ERROR_FOLDER"]

    def createFolders(self) -> None:
        for folder in (self.inboxFolder, self.archiveFolder, self.errorFolder):
            folder.mkdir(parents=True, exist_ok=True)

    def connectionString(self) -> str:
        if self.login == "windows":
            credentials = "Trusted_Connection=yes"
        else:
            credentials = f"UID={self.username};PWD={{{self.password}}}"
        return (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={self.server};DATABASE=master;"
            f"Encrypt=yes;TrustServerCertificate=yes;{credentials}"
        )

    def __str__(self) -> str:
        return f"{self.environment} on {self.server}"
