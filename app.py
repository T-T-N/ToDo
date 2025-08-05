from flask import Flask, render_template, request, jsonify
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime

app = Flask(__name__)

# Database configuration
db_config = {
    'dbname': os.getenv('DB_NAME', 'todolist'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'root'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432')
}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db():
    try:
        conn = psycopg2.connect(**db_config)
        conn.autocommit = True
        return conn, conn.cursor(cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Failed to get database connection: {e}")
        return None, None

def init_db():
    conn, cur = get_db()
    if conn and cur:
        try:
            # Create tasks table if it doesn't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    status VARCHAR(50) DEFAULT 'todo',
                    priority VARCHAR(50) DEFAULT 'medium',
                    due_date DATE,
                    assigned_date DATE,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
        finally:
            cur.close()
            conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    conn, cur = get_db()
    if not conn or not cur:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        tasks = cur.fetchall()
        return jsonify([dict(task) for task in tasks])
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        return jsonify({'error': 'Failed to fetch tasks'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/tasks', methods=['POST'])
def create_task():
    conn, cur = get_db()
    if not conn or not cur:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        task = request.json
        cur.execute("""
            INSERT INTO tasks (title, description, status, priority, due_date, assigned_date, notes)
            VALUES (%(title)s, %(description)s, %(status)s, %(priority)s, %(due_date)s, %(assigned_date)s, %(notes)s)
            RETURNING *
        """, task)
        new_task = dict(cur.fetchone())
        return jsonify(new_task), 201
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return jsonify({'error': 'Failed to create task'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    conn, cur = get_db()
    if not conn or not cur:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        task = request.json
        update_fields = []
        values = {}
        
        for key, value in task.items():
            if key not in ['id']:
                update_fields.append(f"{key} = %({key})s")
                values[key] = value
        
        values['id'] = task_id
        query = f"""
            UPDATE tasks 
            SET {', '.join(update_fields)}
            WHERE id = %(id)s
            RETURNING *
        """
        
        cur.execute(query, values)
        updated_task = dict(cur.fetchone())
        return jsonify(updated_task)
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        return jsonify({'error': 'Failed to update task'}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    conn, cur = get_db()
    if not conn or not cur:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        return '', 204
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        return jsonify({'error': 'Failed to delete task'}), 500
    finally:
        cur.close()
        conn.close()

# Initialize database when app starts
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)