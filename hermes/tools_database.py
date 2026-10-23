"""Database tools for Hermes agent."""
import asyncio
import csv
import json
import os
import pathlib
import sqlite3
# --- константы вынесены FORGE refactor ---
CONST_120 = 120
CONST_500 = 500
CONST_3306 = 3306


TOOLS = [
    {
        "name": "query_sqlite",
        "description": "Execute a SQL query on a SQLite database (SELECT, INSERT, UPDATE, DELETE)",
        "parameters": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Path to SQLite database file"},
                "query": {"type": "string", "description": "SQL query to execute"},
                "params": {"type": "array", "items": {"type": "string"}, "description": "Query parameters for prepared statement"},
            },
            "required": ["db_path", "query"],
        },
    },
    {
        "name": "query_postgres",
        "description": "Execute a SQL query on a PostgreSQL database",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_string": {"type": "string", "description": "PostgreSQL connection string (e.g. 'postgresql://user:pass@host:5432/dbname')"},
                "query": {"type": "string", "description": "SQL query to execute"},
                "params": {"type": "array", "items": {"type": "string"}, "description": "Query parameters"},
            },
            "required": ["connection_string", "query"],
        },
    },
    {
        "name": "query_mysql",
        "description": "Execute a SQL query on a MySQL database",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_string": {"type": "string", "description": "MySQL connection string (e.g. 'mysql://user:pass@host:3306/dbname')"},
                "query": {"type": "string", "description": "SQL query to execute"},
                "params": {"type": "array", "items": {"type": "string"}, "description": "Query parameters"},
            },
            "required": ["connection_string", "query"],
        },
    },
    {
        "name": "backup_database",
        "description": "Backup a database to a file",
        "parameters": {
            "type": "object",
            "properties": {
                "db_type": {"type": "string", "enum": ["sqlite", "postgres", "mysql"], "description": "Database type", "default": "sqlite"},
                "source": {"type": "string", "description": "Database path or connection string"},
                "output_path": {"type": "string", "description": "Backup file path"},
            },
            "required": ["source", "output_path"],
        },
    },
    {
        "name": "restore_database",
        "description": "Restore a database from a backup file",
        "parameters": {
            "type": "object",
            "properties": {
                "db_type": {"type": "string", "enum": ["sqlite", "postgres", "mysql"], "description": "Database type", "default": "sqlite"},
                "source": {"type": "string", "description": "Backup file path"},
                "target": {"type": "string", "description": "Target database path or connection string"},
            },
            "required": ["source", "target"],
        },
    },
    {
        "name": "migrate_schema",
        "description": "Run database schema migration from a SQL file",
        "parameters": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Database path (SQLite) or connection string"},
                "migration_sql": {"type": "string", "description": "SQL migration statements"},
                "db_type": {"type": "string", "enum": ["sqlite", "postgres", "mysql"], "default": "sqlite"},
            },
            "required": ["db_path", "migration_sql"],
        },
    },
    {
        "name": "seed_database",
        "description": "Populate database tables with test data",
        "parameters": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Database path"},
                "table": {"type": "string", "description": "Table to seed"},
                "data": {"type": "string", "description": "JSON array of row objects, e.g. '[{\"name\":\"Alice\",\"age\":30}]'"},
                "count": {"type": "integer", "description": "Number of auto-generated rows (if data not provided)", "default": 10},
            },
            "required": ["db_path", "table"],
        },
    },
    {
        "name": "analyze_query",
        "description": "Analyze query performance using EXPLAIN QUERY PLAN",
        "parameters": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Database path"},
                "query": {"type": "string", "description": "SQL query to analyze"},
            },
            "required": ["db_path", "query"],
        },
    },
    {
        "name": "export_csv",
        "description": "Export query results to a CSV file",
        "parameters": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Database path"},
                "query": {"type": "string", "description": "SELECT query"},
                "output_path": {"type": "string", "description": "Output CSV file path"},
            },
            "required": ["db_path", "query", "output_path"],
        },
    },
    {
        "name": "import_csv",
        "description": "Import CSV data into a database table",
        "parameters": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Database path"},
                "csv_path": {"type": "string", "description": "CSV file path"},
                "table": {"type": "string", "description": "Target table name"},
                "create_table": {"type": "boolean", "description": "Create table if it doesn't exist", "default": True},
            },
            "required": ["db_path", "csv_path", "table"],
        },
    },
]

functions = {}


async def query_sqlite(args):
    db_path = args["db_path"]
    query = args["query"]
    params = args.get("params", [])

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query, params)
        desc = cursor.description
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        columns = [d[0] for d in desc] if desc else []
        return {
            "success": True,
            "rows": rows[:CONST_500],
            "count": len(rows),
            "columns": columns,
            "truncated": len(rows) > CONST_500,
        }
    except Exception as e:
        return {"error": str(e), "success": False}


async def query_postgres(args):
    conn_str = args["connection_string"]
    query = args["query"]
    params = args.get("params", [])

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        return {"error": "psycopg2 not installed. Run: pip install psycopg2-binary", "success": False}

    try:
        conn = psycopg2.connect(conn_str)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query, params or None)
        if cursor.description:
            rows = [dict(row) for row in cursor.fetchall()]
            columns = [d[0] for d in cursor.description]
        else:
            rows = []
            columns = []
            conn.commit()
        conn.close()
        return {"success": True, "rows": rows[:CONST_500], "count": len(rows), "columns": columns, "truncated": len(rows) > CONST_500}
    except Exception as e:
        return {"error": str(e), "success": False}


async def query_mysql(args):
    conn_str = args["connection_string"]
    query = args["query"]
    params = args.get("params", [])

    try:
        import pymysql
        import pymysql.cursors
    except ImportError:
        return {"error": "pymysql not installed. Run: pip install pymysql", "success": False}

    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(conn_str)
        conn = pymysql.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or CONST_3306,
            user=parsed.username or "root",
            password=parsed.password or "",
            database=parsed.path.lstrip("/") or None,
            cursorclass=pymysql.cursors.DictCursor,
        )
        cursor = conn.cursor()
        cursor.execute(query, params or None)
        if cursor.description:
            rows = [dict(row) for row in cursor.fetchall()]
            columns = [d[0] for d in cursor.description]
        else:
            rows = []
            columns = []
            conn.commit()
        conn.close()
        return {"success": True, "rows": rows[:CONST_500], "count": len(rows), "columns": columns, "truncated": len(rows) > CONST_500}
    except Exception as e:
        return {"error": str(e), "success": False}


async def backup_database(args):
    db_type = args.get("db_type", "sqlite")
    source = args["source"]
    output_path = args["output_path"]

    try:
        if db_type == "sqlite":
            if not os.path.exists(source):
                return {"error": f"Database not found: {source}", "success": False}
            conn = sqlite3.connect(source)
            backup_conn = sqlite3.connect(output_path)
            conn.backup(backup_conn)
            backup_conn.close()
            conn.close()
            size = os.path.getsize(output_path)
            return {"success": True, "source": source, "backup": output_path, "size_bytes": size}

        elif db_type in ("postgres", "mysql"):
            if db_type == "postgres":
                tool = "pg_dump"
            else:
                tool = "mysqldump"

            parsed = urllib.parse.urlparse(source)
            cmd = [tool]
            if db_type == "postgres":
                if parsed.username:
                    cmd.extend(["-U", parsed.username])
                if parsed.hostname:
                    cmd.extend(["-h", parsed.hostname])
                if parsed.port:
                    cmd.extend(["-p", str(parsed.port)])
                cmd.extend(["-f", output_path, parsed.path.lstrip("/")])
            else:
                if parsed.username:
                    cmd.extend(["-u", parsed.username])
                if parsed.hostname:
                    cmd.extend(["-h", parsed.hostname])
                if parsed.port:
                    cmd.extend(["-P", str(parsed.port)])
                cmd.extend([parsed.path.lstrip("/"), "-r", output_path])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=CONST_120)
            if proc.returncode != 0:
                return {"error": stderr.decode("utf-8", errors="replace"), "success": False}
            size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            return {"success": True, "source": source, "backup": output_path, "size_bytes": size}
        else:
            return {"error": f"Unsupported db_type: {db_type}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def restore_database(args):
    db_type = args.get("db_type", "sqlite")
    source = args["source"]
    target = args["target"]

    try:
        if db_type == "sqlite":
            import shutil
            shutil.copy2(source, target)
            return {"success": True, "source": source, "target": target}

        elif db_type in ("postgres", "mysql"):
            import urllib.parse
            parsed = urllib.parse.urlparse(target)
            if db_type == "postgres":
                cmd = ["psql"]
                if parsed.username:
                    cmd.extend(["-U", parsed.username])
                if parsed.hostname:
                    cmd.extend(["-h", parsed.hostname])
                if parsed.port:
                    cmd.extend(["-p", str(parsed.port)])
                cmd.extend(["-d", parsed.path.lstrip("/"), "-f", source])
            else:
                cmd = ["mysql"]
                if parsed.username:
                    cmd.extend(["-u", parsed.username])
                if parsed.hostname:
                    cmd.extend(["-h", parsed.hostname])
                if parsed.port:
                    cmd.extend(["-P", str(parsed.port)])
                cmd.append(parsed.path.lstrip("/"))

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=open(source, "r"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=CONST_120)
            if proc.returncode != 0:
                return {"error": stderr.decode("utf-8", errors="replace"), "success": False}
            return {"success": True, "source": source, "target": target}
        else:
            return {"error": f"Unsupported db_type: {db_type}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def migrate_schema(args):
    db_path = args["db_path"]
    migration_sql = args["migration_sql"]
    db_type = args.get("db_type", "sqlite")

    try:
        if db_type == "sqlite":
            conn = sqlite3.connect(db_path)
            statements = [s.strip() for s in migration_sql.split(";") if s.strip()]
            results = []
            for stmt in statements:
                try:
                    conn.execute(stmt)
                    results.append({"statement": stmt[:100], "status": "ok"})
                except Exception as e:
                    results.append({"statement": stmt[:100], "status": "error", "error": str(e)})
            conn.commit()
            conn.close()
            return {"success": True, "db_path": db_path, "statements_executed": len(results), "results": results}

        elif db_type in ("postgres", "mysql"):
            if db_type == "postgres":
                import psycopg2
                conn = psycopg2.connect(db_path)
            else:
                import pymysql
                import urllib.parse
                parsed = urllib.parse.urlparse(db_path)
                conn = pymysql.connect(
                    host=parsed.hostname or "localhost",
                    port=parsed.port or CONST_3306,
                    user=parsed.username or "root",
                    password=parsed.password or "",
                    database=parsed.path.lstrip("/") or None,
                )

            cursor = conn.cursor()
            statements = [s.strip() for s in migration_sql.split(";") if s.strip()]
            results = []
            for stmt in statements:
                try:
                    cursor.execute(stmt)
                    results.append({"statement": stmt[:100], "status": "ok"})
                except Exception as e:
                    results.append({"statement": stmt[:100], "status": "error", "error": str(e)})
            conn.commit()
            conn.close()
            return {"success": True, "db_path": db_path, "statements_executed": len(results), "results": results}
        else:
            return {"error": f"Unsupported db_type: {db_type}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def seed_database(args):
    db_path = args["db_path"]
    table = args["table"]
    data_str = args.get("data", "")
    count = args.get("count", 10)

    try:
        conn = sqlite3.connect(db_path)

        cursor = conn.execute(f"PRAGMA table_info('{table}')")
        columns_info = cursor.fetchall()
        if not columns_info:
            conn.close()
            return {"error": f"Table '{table}' not found", "success": False}

        columns = [(row[1], row[2]) for row in columns_info]

        if data_str:
            rows_data = json.loads(data_str)
        else:
            import random
            import string
            rows_data = []
            for i in range(count):
                row = {}
                for col_name, col_type in columns:
                    if col_name.lower() in ("id",):
                        continue
                    ct = col_type.upper()
                    if "INT" in ct:
                        row[col_name] = random.randint(1, 10000)
                    elif "REAL" in ct or "FLOAT" in ct or "DOUBLE" in ct:
                        row[col_name] = round(random.uniform(1.0, 1000.0), 2)
                    elif "BLOB" in ct:
                        row[col_name] = os.urandom(8).hex()
                    else:
                        row[col_name] = f"test_{i}_{col_name}"
                rows_data.append(row)

        inserted = 0
        for row in rows_data:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(["?" for _ in row])
            try:
                conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(row.values()))
                inserted += 1
            except Exception:
                continue
        conn.commit()
        conn.close()
        return {"success": True, "table": table, "rows_inserted": inserted, "total_requested": len(rows_data)}
    except Exception as e:
        return {"error": str(e), "success": False}


async def analyze_query(args):
    db_path = args["db_path"]
    query = args["query"]

    try:
        conn = sqlite3.connect(db_path)

        explain_query = f"EXPLAIN QUERY PLAN {query}"
        cursor = conn.execute(explain_query)
        plan_rows = [dict(zip(["id", "parent", "detail"], row)) for row in cursor.fetchall()]

        cursor = conn.execute(query)
        col_names = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchall()

        stats = {
            "rows_returned": len(rows),
            "columns": col_names,
            "explain_plan": plan_rows,
        }

        if len(rows) > 0:
            stats["sample_row"] = dict(zip(col_names, rows[0]))

        conn.close()
        return {"success": True, "query": query, "analysis": stats}
    except Exception as e:
        return {"error": str(e), "success": False}


async def export_csv(args):
    db_path = args["db_path"]
    query = args["query"]
    output_path = args["output_path"]

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(query)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        output = pathlib.Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

        return {"success": True, "output": output_path, "rows_exported": len(rows), "columns": columns}
    except Exception as e:
        return {"error": str(e), "success": False}


async def import_csv(args):
    db_path = args["db_path"]
    csv_path = args["csv_path"]
    table = args["table"]
    create_table = args.get("create_table", True)

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
            rows = list(reader)

        conn = sqlite3.connect(db_path)

        if create_table:
            col_defs = ", ".join([f'"{h}" TEXT' for h in headers])
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({col_defs})")

        placeholders = ", ".join(["?" for _ in headers])
        cols = ", ".join([f'"{h}"' for h in headers])

        inserted = 0
        for row in rows:
            if len(row) == len(headers):
                conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", row)
                inserted += 1

        conn.commit()
        conn.close()

        return {"success": True, "table": table, "rows_imported": inserted, "columns": headers, "csv_file": csv_path}
    except Exception as e:
        return {"error": str(e), "success": False}


functions = {
    "query_sqlite": query_sqlite,
    "query_postgres": query_postgres,
    "query_mysql": query_mysql,
    "backup_database": backup_database,
    "restore_database": restore_database,
    "migrate_schema": migrate_schema,
    "seed_database": seed_database,
    "analyze_query": analyze_query,
    "export_csv": export_csv,
    "import_csv": import_csv,
}
