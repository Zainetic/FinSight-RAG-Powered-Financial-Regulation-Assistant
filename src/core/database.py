import os
import psycopg2
from psycopg2.extras import Json
from datetime import datetime
from dotenv import load_dotenv

# Load the database credentials from the .env file
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    """Helper function to establish a Postgres connection."""
    if not DATABASE_URL:
        raise ValueError("CRITICAL ERROR: DATABASE_URL missing")
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Initializes the PostgreSQL database and creates the audit table if missing."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compliance_logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                user_query TEXT NOT NULL,
                risk_category VARCHAR(50) NOT NULL,
                is_compliant BOOLEAN NOT NULL,
                full_json_payload JSONB NOT NULL
            )
        """)

        conn.commit()
    except Exception as e:
        print(f"Database initialization failed: {e}")
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()


def save_compliance_record(user_query: str, result_dict: dict):
    """
    Extracts the indexed fields and writes the full payload to a JSONB column.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        timestamp = datetime.now()
        risk_category = result_dict.get("risk_category", "Unknown")
        is_compliant = result_dict.get("is_compliant", False)

        # psycopg2.extras.Json securely handles the dict-to-JSONB conversion
        cursor.execute("""
            INSERT INTO compliance_logs 
            (timestamp, user_query, risk_category, is_compliant, full_json_payload)
            VALUES (%s, %s, %s, %s, %s)
        """, (timestamp, user_query, risk_category, is_compliant, Json(result_dict)))

        conn.commit()
        print("Payload successfully routed to PostgreSQL JSONB storage.")

    except Exception as e:
        print(f"Failed to save record to PostgreSQL: {e}")
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()


# Initialize the table when the module loads
init_db()