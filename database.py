import sqlite3
import os
from datetime import datetime
from typing import Optional
import json

DATABASE_PATH = "payment_requests.db"
UPLOADS_DIR = "uploads"

def get_connection():
    """Get database connection with row factory for dict-like access."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize database tables if they don't exist."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)

    conn = get_connection()
    cursor = conn.cursor()

    # Payment requests table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_name TEXT NOT NULL,
            provider_id TEXT,
            purchase_order_number TEXT,
            np_type TEXT,  -- 'NPA', 'NPV', 'NPW', 'NPM'
            np_number TEXT,  -- número de nota de pedido
            amount REAL NOT NULL,
            payment_type TEXT NOT NULL,  -- 'total' or 'parcial'
            payment_method TEXT NOT NULL,  -- 'transferencia' or 'e-cheq'
            payment_term TEXT,  -- plazo de pago
            agreed_payment_date DATE,
            mockup_path TEXT,
            invoice_path TEXT,
            requested_by TEXT NOT NULL,
            status TEXT DEFAULT 'pendiente',  -- 'pendiente', 'aprobado_cfo', 'en_proceso', 'completado', 'rechazado'
            cfo_approved INTEGER DEFAULT 0,  -- 0 = no aprobado, 1 = aprobado
            cfo_approved_by TEXT,
            cfo_approved_at TIMESTAMP,
            admin_notes TEXT,
            payment_proof_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    # Users table (simple list of users)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            team TEXT NOT NULL  -- 'produccion' or 'admin'
        )
    """)

    # Providers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id TEXT UNIQUE,
            name TEXT NOT NULL,
            payment_condition TEXT  -- condición de pago por defecto del proveedor
        )
    """)

    # Add payment_condition column if it doesn't exist (migration for existing DBs)
    cursor.execute("PRAGMA table_info(providers)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'payment_condition' not in columns:
        cursor.execute("ALTER TABLE providers ADD COLUMN payment_condition TEXT")

    # Add new columns for NP and CFO approval (migration for existing DBs)
    cursor.execute("PRAGMA table_info(payment_requests)")
    pr_columns = [col[1] for col in cursor.fetchall()]

    if 'np_type' not in pr_columns:
        cursor.execute("ALTER TABLE payment_requests ADD COLUMN np_type TEXT")
    if 'np_number' not in pr_columns:
        cursor.execute("ALTER TABLE payment_requests ADD COLUMN np_number TEXT")
    if 'cfo_approved' not in pr_columns:
        cursor.execute("ALTER TABLE payment_requests ADD COLUMN cfo_approved INTEGER DEFAULT 0")
    if 'cfo_approved_by' not in pr_columns:
        cursor.execute("ALTER TABLE payment_requests ADD COLUMN cfo_approved_by TEXT")
    if 'cfo_approved_at' not in pr_columns:
        cursor.execute("ALTER TABLE payment_requests ADD COLUMN cfo_approved_at TIMESTAMP")

    # Insert default users if table is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        default_users = [
            ("Usuario Producción 1", "produccion"),
            ("Usuario Producción 2", "produccion"),
            ("Usuario Admin 1", "admin"),
            ("Usuario Admin 2", "admin"),
        ]
        cursor.executemany("INSERT INTO users (name, team) VALUES (?, ?)", default_users)

    conn.commit()
    conn.close()

def get_users(team: Optional[str] = None) -> list:
    """Get list of users, optionally filtered by team."""
    conn = get_connection()
    cursor = conn.cursor()

    if team:
        cursor.execute("SELECT * FROM users WHERE team = ?", (team,))
    else:
        cursor.execute("SELECT * FROM users")

    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users

def add_user(name: str, team: str) -> bool:
    """Add a new user."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (name, team) VALUES (?, ?)", (name, team))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_user(user_id: int) -> bool:
    """Delete a user by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

def get_providers() -> list:
    """Get list of all providers."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM providers ORDER BY name")
    providers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return providers

def add_provider(name: str, provider_id: str = None, payment_condition: str = None) -> bool:
    """Add a new provider."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO providers (name, provider_id, payment_condition) VALUES (?, ?, ?)",
            (name, provider_id, payment_condition)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_provider_by_name(name: str) -> Optional[dict]:
    """Get a provider by name."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM providers WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_payment_request(data: dict) -> int:
    """Create a new payment request. Returns the ID of the created request."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO payment_requests (
            provider_name, provider_id, purchase_order_number, np_type, np_number,
            amount, payment_type, payment_method, payment_term, agreed_payment_date,
            mockup_path, invoice_path, requested_by, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente')
    """, (
        data['provider_name'],
        data.get('provider_id'),
        data.get('purchase_order_number'),
        data.get('np_type'),
        data.get('np_number'),
        data['amount'],
        data['payment_type'],
        data['payment_method'],
        data.get('payment_term'),
        data.get('agreed_payment_date'),
        data.get('mockup_path'),
        data.get('invoice_path'),
        data['requested_by']
    ))

    request_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return request_id

def get_payment_requests(status: Optional[str] = None) -> list:
    """Get all payment requests, optionally filtered by status."""
    conn = get_connection()
    cursor = conn.cursor()

    if status:
        cursor.execute(
            "SELECT * FROM payment_requests WHERE status = ? ORDER BY created_at DESC",
            (status,)
        )
    else:
        cursor.execute("SELECT * FROM payment_requests ORDER BY created_at DESC")

    requests = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return requests

def get_payment_request(request_id: int) -> Optional[dict]:
    """Get a single payment request by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_payment_status(request_id: int, status: str, admin_notes: str = None,
                          payment_proof_path: str = None) -> bool:
    """Update the status of a payment request."""
    conn = get_connection()
    cursor = conn.cursor()

    update_fields = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
    params = [status]

    if admin_notes is not None:
        update_fields.append("admin_notes = ?")
        params.append(admin_notes)

    if payment_proof_path is not None:
        update_fields.append("payment_proof_path = ?")
        params.append(payment_proof_path)

    if status == 'completado':
        update_fields.append("completed_at = CURRENT_TIMESTAMP")

    params.append(request_id)

    cursor.execute(
        f"UPDATE payment_requests SET {', '.join(update_fields)} WHERE id = ?",
        params
    )

    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def approve_cfo(request_id: int, approved_by: str) -> bool:
    """CFO approves a payment request."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE payment_requests
        SET cfo_approved = 1,
            cfo_approved_by = ?,
            cfo_approved_at = CURRENT_TIMESTAMP,
            status = 'aprobado_cfo',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (approved_by, request_id))

    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def reject_cfo(request_id: int, approved_by: str, reason: str = None) -> bool:
    """CFO rejects a payment request."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE payment_requests
        SET cfo_approved = 0,
            cfo_approved_by = ?,
            cfo_approved_at = CURRENT_TIMESTAMP,
            status = 'rechazado',
            admin_notes = COALESCE(admin_notes || ' | ', '') || ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (approved_by, f"Rechazado por CFO: {reason or 'Sin motivo especificado'}", request_id))

    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

def get_stats() -> dict:
    """Get statistics about payment requests."""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    # Count by status
    cursor.execute("""
        SELECT status, COUNT(*) as count, SUM(amount) as total
        FROM payment_requests
        GROUP BY status
    """)

    for row in cursor.fetchall():
        stats[row['status']] = {
            'count': row['count'],
            'total': row['total'] or 0
        }

    conn.close()
    return stats
