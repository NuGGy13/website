import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_NAME = "chat_logs.db"
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = str(BASE_DIR / DB_NAME)
DEFAULT_BACKUP_DIR_NAME = "chat_log_backups"
DESKTOP_BACKUP_DIR = Path.home() / "Desktop" / DEFAULT_BACKUP_DIR_NAME
USER_LOG_FILE = Path.home() / "Desktop" / "user_credentials_log.txt"


def _resolve_db_path(db_path=None):
    if db_path:
        return str(Path(db_path).expanduser())
    return DEFAULT_DB_PATH


def init_db(db_path=None):
    """Create the logs table if it does not already exist."""
    resolved_path = _resolve_db_path(db_path)
    conn = sqlite3.connect(resolved_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS interaction_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_id TEXT,
            model_used TEXT,
            prompt TEXT NOT NULL,
            response TEXT,
            error TEXT,
            status TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    return resolved_path


def log_interaction(prompt, response=None, error=None, model_used="default", user_id="anonymous", db_path=None, export_to_desktop=True):
    """Save a prompt, response, or error event to the database and optionally export a daily backup to the desktop."""
    resolved_path = init_db(db_path)
    conn = sqlite3.connect(resolved_path)
    cursor = conn.cursor()

    status = "SUCCESS" if error is None else "ERROR"
    timestamp = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """
        INSERT INTO interaction_logs (timestamp, user_id, model_used, prompt, response, error, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            user_id,
            model_used,
            str(prompt),
            None if response is None else str(response),
            None if error is None else str(error),
            status,
        ),
    )

    conn.commit()
    conn.close()

    if export_to_desktop:
        export_daily_backup(db_path=resolved_path)

    return resolved_path


def export_daily_backup(db_path=None, backup_dir=None):
    """Export the current logs to a timestamped CSV file in a backup folder on the desktop."""
    resolved_db_path = _resolve_db_path(db_path)
    target_dir = Path(backup_dir or DESKTOP_BACKUP_DIR).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target_path = target_dir / f"chat_logs_{timestamp}.csv"

    conn = sqlite3.connect(resolved_db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, timestamp, user_id, model_used, prompt, response, error, status FROM interaction_logs ORDER BY id"
    ).fetchall()
    conn.close()

    with target_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "timestamp", "user_id", "model_used", "prompt", "response", "error", "status"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})

    return str(target_path)


def log_user_credentials(username, password, source="app"):
    """Append a username/password entry to a separate desktop log file."""
    USER_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with USER_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] source={source} username={username} password={password}\n")
    return str(USER_LOG_FILE)