"""Database management tools for Hermes agent."""
import asyncio
import json
import os
import sqlite3

TOOLS = [
    {"name": "db_query", "description": "Execute a read-only SQL query on SQLite database", "parameters": {"type": "object", "properties": {"db_path": {"type": "string", "description": "Path to SQLite database"}, "query": {"type": "string", "description": "SQL query (SELECT only)"}}, "required": ["db_path", "query"]}},
    {"name": "db_schema", "description": "Get database schema (tables, columns, types)", "parameters": {"type": "object", "properties": {"db_path": {"type": "string", "description": "Path to SQLite database"}}, "required": ["db_path"]}},
    {"name": "db_backup", "description": "Backup a SQLite database", "parameters": {"type": "object", "properties": {"db_path": {"type": "string", "description": "Source database path"}, "backup_path": {"type": "string", "description": "Backup destination path"}}, "required": ["db_path", "backup_path"]}},
    {"name": "db_analyze", "description": "Analyze database size, row counts, and index usage", "parameters": {"type": "object", "properties": {"db_path": {"type": "string", "description": "Path to SQLite database"}}, "required": ["db_path"]}},
    {"name": "db_create_table", "description": "Create a table in SQLite database", "parameters": {"type": "object", "properties": {"db_path": {"type": "string", "description": "Database path"}, "table_name": {"type": "string", "description": "Table name"}, "columns": {"type": "string", "description": "Column definitions (e.g. 'id INTEGER PRIMARY KEY, name TEXT')"}}, "required": ["db_path", "table_name", "columns"]}},
    {"name": "db_insert", "description": "Insert a row into a SQLite table", "parameters": {"type": "object", "properties": {"db_path": {"type": "string"}, "table": {"type": "string"}, "data": {"type": "string", "description": "JSON object of column:value pairs"}}, "required": ["db_path", "table", "data"]}},
    {"name": "db_export_csv", "description": "Export query results to CSV", "parameters": {"type": "object", "properties": {"db_path": {"type": "string"}, "query": {"type": "string"}, "output": {"type": "string", "description": "Output CSV file path"}}, "required": ["db_path", "query", "output"]}},
    {"name": "db_optimize", "description": "Optimize database (VACUUM, ANALYZE)", "parameters": {"type": "object", "properties": {"db_path": {"type": "string"}}, "required": ["db_path"]}},
]

functions = {}

async def db_query(args):
    db_path = args["db_path"]
    query = args["query"]

    if not query.strip().upper().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries are allowed for safety"})

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return json.dumps({"rows": rows[:1000], "count": len(rows), "query": query})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def db_schema(args):
    db_path = args["db_path"]
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]

        schema = {}
        for table in tables:
            cursor = conn.execute(f"PRAGMA table_info('{table}')")
            columns = [{"name": row[1], "type": row[2], "notnull": bool(row[3]), "pk": bool(row[5])} for row in cursor.fetchall()]
            cursor = conn.execute(f"SELECT COUNT(*) FROM '{table}'")
            row_count = cursor.fetchone()[0]
            schema[table] = {"columns": columns, "row_count": row_count}

        conn.close()
        return json.dumps({"tables": tables, "schema": schema, "table_count": len(tables)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def db_backup(args):
    db_path = args["db_path"]
    backup_path = args["backup_path"]
    try:
        conn = sqlite3.connect(db_path)
        backup_conn = sqlite3.connect(backup_path)
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()
        size = os.path.getsize(backup_path)
        return json.dumps({"success": True, "source": db_path, "backup": backup_path, "size_bytes": size})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def db_analyze(args):
    db_path = args["db_path"]
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        analysis = {}
        for table in tables:
            cursor = conn.execute(f"PRAGMA table_info('{table}')")
            cols = len(cursor.fetchall())
            cursor = conn.execute(f"SELECT COUNT(*) FROM '{table}'")
            rows = cursor.fetchone()[0]
            cursor = conn.execute(f"PRAGMA index_list('{table}')")
            indexes = len(cursor.fetchall())
            analysis[table] = {"columns": cols, "rows": rows, "indexes": indexes}

        file_size = os.path.getsize(db_path)
        conn.close()
        return json.dumps({"database": db_path, "file_size_bytes": file_size, "file_size_mb": round(file_size / 1024 / 1024, 2), "tables": analysis, "table_count": len(tables)})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def db_create_table(args):
    db_path = args["db_path"]
    table = args["table_name"]
    columns = args["columns"]
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({columns})")
        conn.commit()
        conn.close()
        return json.dumps({"success": True, "table": table, "columns": columns})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def db_insert(args):
    db_path = args["db_path"]
    table = args["table"]
    data = json.loads(args["data"])
    try:
        conn = sqlite3.connect(db_path)
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(data.values()))
        conn.commit()
        conn.close()
        return json.dumps({"success": True, "table": table, "inserted": data})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def db_export_csv(args):
    db_path = args["db_path"]
    query = args["query"]
    output = args["output"]
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(query)
        headers = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        import csv
        with open(output, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        return json.dumps({"success": True, "output": output, "rows": len(rows), "columns": headers})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def db_optimize(args):
    db_path = args["db_path"]
    try:
        size_before = os.path.getsize(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
        conn.close()
        size_after = os.path.getsize(db_path)
        return json.dumps({"success": True, "size_before": size_before, "size_after": size_after, "freed_bytes": size_before - size_after})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "db_query": db_query, "db_schema": db_schema, "db_backup": db_backup,
    "db_analyze": db_analyze, "db_create_table": db_create_table, "db_insert": db_insert,
    "db_export_csv": db_export_csv, "db_optimize": db_optimize,
}
