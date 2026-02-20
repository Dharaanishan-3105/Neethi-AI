#!/usr/bin/env python3
"""
Database migration script to add missing columns to existing tables.
Run this once to fix the Render database schema.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()


def migrate_database():
    """Add missing columns to the database."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # Use local database for development
        database_url = "postgresql://neethi_user:HariDharaan%402025@localhost/neethi_ai"
        print("Using local database for migration")
    else:
        print("Using production database for migration")

    try:
        # Create engine
        engine = create_engine(database_url)

        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()

            try:
                # Check if conversation_id column exists in chat table
                result = conn.execute(
                    text(
                        """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'chat' AND column_name = 'conversation_id'
                """
                    )
                )

                if not result.fetchone():
                    print("Adding conversation_id column to chat table...")
                    conn.execute(
                        text(
                            """
                        ALTER TABLE chat 
                        ADD COLUMN conversation_id INTEGER REFERENCES conversation(id)
                    """
                        )
                    )
                    print("conversation_id column added")
                else:
                    print("conversation_id column already exists")

                # Check if is_edited column exists
                result = conn.execute(
                    text(
                        """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'chat' AND column_name = 'is_edited'
                """
                    )
                )

                if not result.fetchone():
                    print("Adding is_edited column to chat table...")
                    conn.execute(
                        text(
                            """
                        ALTER TABLE chat 
                        ADD COLUMN is_edited BOOLEAN DEFAULT FALSE
                    """
                        )
                    )
                    print("is_edited column added")
                else:
                    print("is_edited column already exists")

                # Check if edited_at column exists
                result = conn.execute(
                    text(
                        """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'chat' AND column_name = 'edited_at'
                """
                    )
                )

                if not result.fetchone():
                    print("Adding edited_at column to chat table...")
                    conn.execute(
                        text(
                            """
                        ALTER TABLE chat 
                        ADD COLUMN edited_at TIMESTAMP
                    """
                        )
                    )
                    print("edited_at column added")
                else:
                    print("edited_at column already exists")

                # Check if chat_encrypted column exists
                result = conn.execute(
                    text(
                        """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'chat' AND column_name = 'chat_encrypted'
                """
                    )
                )

                if not result.fetchone():
                    print("Adding chat_encrypted column to chat table...")
                    conn.execute(
                        text(
                            """
                        ALTER TABLE chat 
                        ADD COLUMN chat_encrypted BOOLEAN DEFAULT FALSE
                    """
                        )
                    )
                    print("chat_encrypted column added")
                else:
                    print("chat_encrypted column already exists")

                # Check if chat_iv column exists
                result = conn.execute(
                    text(
                        """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'chat' AND column_name = 'chat_iv'
                """
                    )
                )

                if not result.fetchone():
                    print("Adding chat_iv column to chat table...")
                    conn.execute(
                        text(
                            """
                        ALTER TABLE chat 
                        ADD COLUMN chat_iv TEXT
                    """
                        )
                    )
                    print("chat_iv column added")
                else:
                    print("chat_iv column already exists")

                # Check if chat_tag column exists
                result = conn.execute(
                    text(
                        """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'chat' AND column_name = 'chat_tag'
                """
                    )
                )

                if not result.fetchone():
                    print("Adding chat_tag column to chat table...")
                    conn.execute(
                        text(
                            """
                        ALTER TABLE chat 
                        ADD COLUMN chat_tag TEXT
                    """
                        )
                    )
                    print("chat_tag column added")
                else:
                    print("chat_tag column already exists")

                # Check if enc_version column exists
                result = conn.execute(
                    text(
                        """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'chat' AND column_name = 'enc_version'
                """
                    )
                )

                if not result.fetchone():
                    print("Adding enc_version column to chat table...")
                    conn.execute(
                        text(
                            """
                        ALTER TABLE chat 
                        ADD COLUMN enc_version SMALLINT DEFAULT 1
                    """
                        )
                    )
                    print("enc_version column added")
                else:
                    print("enc_version column already exists")

                # Check if key_id column exists
                result = conn.execute(
                    text(
                        """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'chat' AND column_name = 'key_id'
                """
                    )
                )

                if not result.fetchone():
                    print("Adding key_id column to chat table...")
                    conn.execute(
                        text(
                            """
                        ALTER TABLE chat 
                        ADD COLUMN key_id TEXT
                    """
                        )
                    )
                    print("key_id column added")
                else:
                    print("key_id column already exists")

                # Commit transaction
                trans.commit()
                print("\nDatabase migration completed successfully!")
                return True

            except Exception as e:
                # Rollback on error
                trans.rollback()
                print(f"Migration failed: {e}")
                return False

    except Exception as e:
        print(f"Database connection failed: {e}")
        return False


if __name__ == "__main__":
    print("Starting database migration...")
    success = migrate_database()
    if success:
        print("Migration completed! Your app should now work on Render.")
    else:
        print("Migration failed. Check the errors above.")
        sys.exit(1)
