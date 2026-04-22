import { spawn } from "node:child_process";

export type SqliteArtifactSnapshot = {
  path: string;
  fileSha256: string;
  fileSizeBytes: number;
  tableCounts: Record<string, number>;
  users: Array<{ username: string; isAdmin: boolean }>;
  dataSha256: string;
};

const SQLITE_ARTIFACT_SCRIPT = `
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

TABLE_SPECS = {
    "users": {
        "select": "username, COALESCE(is_admin, 0)",
        "order_by": ("username",),
    },
    "recurring_bills": {
        "select": "user_id, name, COALESCE(amount_cents, -1), COALESCE(merchant_canonical, ''), COALESCE(active, 0), anchor_date, frequency, interval_value",
        "order_by": ("user_id", "name", "id"),
    },
    "recurring_bill_occurrences": {
        "select": "bill_id, due_date, status, COALESCE(expected_amount_cents, -1), COALESCE(actual_amount_cents, -1)",
        "order_by": ("bill_id", "due_date", "id"),
    },
    "cashflow_entries": {
        "select": "user_id, effective_date, direction, category, amount_cents, COALESCE(source_type, ''), COALESCE(linked_transaction_id, '')",
        "order_by": ("user_id", "effective_date", "id"),
    },
    "budget_months": {
        "select": "user_id, year, month, COALESCE(planned_income_cents, -1), COALESCE(target_savings_cents, -1), COALESCE(opening_balance_cents, -1)",
        "order_by": ("user_id", "year", "month", "id"),
    },
    "budget_rules": {
        "select": "user_id, scope_type, scope_value, period, amount_cents, COALESCE(active, 0)",
        "order_by": ("user_id", "scope_type", "scope_value", "rule_id", "id"),
    },
}


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows if len(row) > 1 and row[1]}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def normalize_rows(rows):
    return [[value for value in row] for row in rows]


def copy_sqlite(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        target_path.unlink()
    source_connection = sqlite3.connect(str(source_path))
    destination_connection = sqlite3.connect(target_path)
    try:
        destination_connection.execute("PRAGMA journal_mode=DELETE")
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()


def snapshot_sqlite(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(str(path))
    try:
        table_counts = {}
        table_rows = {}
        for table_name, spec in TABLE_SPECS.items():
            if not table_exists(connection, table_name):
                continue
            available_columns = table_columns(connection, table_name)
            order_columns = [column for column in spec["order_by"] if column in available_columns]
            query = f"SELECT {spec['select']} FROM {table_name}"
            if order_columns:
                query = f"{query} ORDER BY {', '.join(order_columns)}"
            count = int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0] or 0)
            rows = normalize_rows(connection.execute(query).fetchall())
            table_counts[table_name] = count
            table_rows[table_name] = rows

        users = [
            {"username": row[0], "isAdmin": bool(row[1])}
            for row in table_rows.get("users", [])
        ]
        canonical = json.dumps(
            {"table_counts": table_counts, "table_rows": table_rows},
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "path": str(path),
            "fileSha256": file_sha256(path),
            "fileSizeBytes": path.stat().st_size,
            "tableCounts": table_counts,
            "users": users,
            "dataSha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }
    finally:
        connection.close()


def main() -> int:
    if len(sys.argv) < 3:
        raise RuntimeError("expected mode and sqlite path arguments")

    mode = sys.argv[1].strip().lower()
    if mode == "copy":
        if len(sys.argv) != 4:
            raise RuntimeError("copy mode requires source and target paths")
        source_path = Path(sys.argv[2]).expanduser().resolve()
        target_path = Path(sys.argv[3]).expanduser().resolve()
        copy_sqlite(source_path, target_path)
        print(json.dumps({"ok": True, "source": str(source_path), "target": str(target_path)}))
        return 0

    if mode == "snapshot":
        path = Path(sys.argv[2]).expanduser().resolve()
        print(json.dumps(snapshot_sqlite(path)))
        return 0

    raise RuntimeError(f"unsupported sqlite artifact mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
`;

async function runPythonJson<T>(
  args: string[],
  { pythonExecutable, env }: { pythonExecutable: string; env: NodeJS.ProcessEnv }
): Promise<T> {
  return await new Promise<T>((resolve, reject) => {
    const proc = spawn(pythonExecutable, ["-c", SQLITE_ARTIFACT_SCRIPT, ...args], {
      env,
      stdio: "pipe"
    });
    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf-8");
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf-8");
    });
    proc.on("error", (error) => {
      reject(error);
    });
    proc.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(
            `SQLite helper exited with code ${String(code)}.${stderr.trim() ? ` ${stderr.trim()}` : ""}`
          )
        );
        return;
      }
      try {
        resolve(JSON.parse(stdout.trim()) as T);
      } catch (error) {
        reject(
          new Error(
            `SQLite helper returned invalid JSON.${stdout.trim() ? ` ${stdout.trim()}` : ""}`
          )
        );
      }
    });
  });
}

export async function copySqliteArtifact(
  sourcePath: string,
  targetPath: string,
  { pythonExecutable, env }: { pythonExecutable: string; env: NodeJS.ProcessEnv }
): Promise<void> {
  await runPythonJson(["copy", sourcePath, targetPath], { pythonExecutable, env });
}

export async function snapshotSqliteArtifact(
  dbPath: string,
  { pythonExecutable, env }: { pythonExecutable: string; env: NodeJS.ProcessEnv }
): Promise<SqliteArtifactSnapshot> {
  return await runPythonJson<SqliteArtifactSnapshot>(["snapshot", dbPath], {
    pythonExecutable,
    env
  });
}

export function describeSqliteSnapshotMismatch(
  expected: SqliteArtifactSnapshot,
  actual: SqliteArtifactSnapshot
): string[] {
  const mismatches: string[] = [];
  if (expected.dataSha256 !== actual.dataSha256) {
    mismatches.push(
      `data hash mismatch (${expected.dataSha256} != ${actual.dataSha256})`
    );
  }

  const expectedCounts = JSON.stringify(expected.tableCounts);
  const actualCounts = JSON.stringify(actual.tableCounts);
  if (expectedCounts !== actualCounts) {
    mismatches.push(`table counts mismatch (${expectedCounts} != ${actualCounts})`);
  }

  const expectedUsers = JSON.stringify(expected.users);
  const actualUsers = JSON.stringify(actual.users);
  if (expectedUsers !== actualUsers) {
    mismatches.push(`users mismatch (${expectedUsers} != ${actualUsers})`);
  }

  return mismatches;
}
