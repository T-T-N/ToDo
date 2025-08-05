from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import logging

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create connection pool for production
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=os.environ.get('DATABASE_URL'),
        cursor_factory=RealDictCursor
    )
    logger.info("Database connection pool created successfully")
except Exception as e:
    logger.error(f"Failed to create database pool: {e}")
    raise

def get_db():
    try:
        conn = db_pool.getconn()
        return conn, conn.cursor()
    except Exception as e:
        logger.error(f"Failed to get database connection: {e}")
        raise

def release_db(conn, cur):
    try:
        cur.close()
        db_pool.putconn(conn)
    except Exception as e:
        logger.error(f"Failed to release database connection: {e}")

# Initialize database table on startup
def init_db():
    conn, cur = get_db()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                due_date DATE,
                assigned_date DATE,
                priority TEXT NOT NULL DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'todo',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create index for better performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_assigned_date ON tasks(assigned_date);
        """)
        
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        release_db(conn, cur)

# Initialize database on startup
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/health')
def health_check():
    try:
        conn, cur = get_db()
        cur.execute("SELECT 1;")
        cur.fetchone()
        release_db(conn, cur)
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'unhealthy', 'database': 'disconnected'}), 500

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    try:
        conn, cur = get_db()
        cur.execute("SELECT * FROM tasks ORDER BY id;")
        rows = cur.fetchall()
        release_db(conn, cur)
        
        # Convert date objects to strings for JSON serialization
        tasks = []
        for row in rows:
            task = dict(row)
            if task['due_date']:
                task['due_date'] = task['due_date'].strftime('%Y-%m-%d')
            if task['assigned_date']:
                task['assigned_date'] = task['assigned_date'].strftime('%Y-%m-%d')
            tasks.append(task)
        
        return jsonify(tasks)
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        return jsonify({'error': 'Failed to fetch tasks'}), 500

@app.route('/api/tasks', methods=['POST'])
def add_task():
    try:
        data = request.json
        conn, cur = get_db()
        cur.execute("""
            INSERT INTO tasks
                (title, description, due_date, assigned_date, priority, status, notes)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            data['title'],
            data.get('description', ''),
            data.get('due_date') if data.get('due_date') else None,
            data.get('assigned_date') if data.get('assigned_date') else None,
            data.get('priority', 'medium'),
            data.get('status', 'todo'),
            data.get('notes', '')
        ))
        new_id = cur.fetchone()['id']
        conn.commit()
        release_db(conn, cur)
        return jsonify({'success': True, 'id': new_id})
    except Exception as e:
        logger.error(f"Error adding task: {e}")
        return jsonify({'error': 'Failed to add task'}), 500

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    try:
        data = request.json
        conn, cur = get_db()
        
        cur.execute("""
            UPDATE tasks SET
                title = COALESCE(%s, title),
                description = COALESCE(%s, description),
                due_date = CASE WHEN %s = '' THEN NULL ELSE COALESCE(%s, due_date) END,
                assigned_date = CASE WHEN %s = '' THEN NULL ELSE COALESCE(%s, assigned_date) END,
                priority = COALESCE(%s, priority),
                status = COALESCE(%s, status),
                notes = COALESCE(%s, notes),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s;
        """, (
            data.get('title'),
            data.get('description'),
            data.get('due_date', ''),
            data.get('due_date'),
            data.get('assigned_date', ''),
            data.get('assigned_date'),
            data.get('priority'),
            data.get('status'),
            data.get('notes'),
            task_id
        ))
        
        if cur.rowcount == 0:
            release_db(conn, cur)
            return jsonify({'error': 'Task not found'}), 404
        
        conn.commit()
        release_db(conn, cur)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        return jsonify({'error': 'Failed to update task'}), 500

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    try:
        conn, cur = get_db()
        cur.execute("DELETE FROM tasks WHERE id = %s;", (task_id,))
        
        if cur.rowcount == 0:
            release_db(conn, cur)
            return jsonify({'error': 'Task not found'}), 404
        
        conn.commit()
        release_db(conn, cur)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        return jsonify({'error': 'Failed to delete task'}), 500

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Create the HTML template
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Calendar</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            color: #333;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        .header {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }

        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }

        .tab {
            background: rgba(255, 255, 255, 0.7);
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            cursor: pointer;
            transition: all 0.3s ease;
            color: #555;
            font-weight: 500;
        }

        .tab.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }

        .tab:hover:not(.active) {
            background: rgba(255, 255, 255, 0.9);
            transform: translateY(-2px);
        }

        .content {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            min-height: 600px;
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        /* Task Tab Styles */
        .view-toggle {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }

        .view-btn {
            background: rgba(102, 126, 234, 0.1);
            border: 2px solid rgba(102, 126, 234, 0.3);
            padding: 8px 16px;
            border-radius: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
            color: #667eea;
            font-weight: 500;
        }

        .view-btn.active {
            background: #667eea;
            color: white;
        }

        .add-task-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            cursor: pointer;
            margin-bottom: 20px;
            font-weight: 500;
            transition: all 0.3s ease;
        }

        .add-task-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
        }

        /* Kanban Board */
        .kanban-board {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }

        .kanban-column {
            background: rgba(248, 249, 250, 0.8);
            border-radius: 15px;
            padding: 20px;
            min-height: 400px;
        }

        .kanban-header {
            font-weight: 600;
            margin-bottom: 15px;
            padding: 10px;
            border-radius: 10px;
            text-align: center;
        }

        .todo-header { background: rgba(255, 193, 7, 0.2); color: #856404; }
        .progress-header { background: rgba(0, 123, 255, 0.2); color: #004085; }
        .done-header { background: rgba(40, 167, 69, 0.2); color: #155724; }

        .task-card {
            background: white;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 10px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
            cursor: move;
            transition: all 0.3s ease;
            border-left: 4px solid #667eea;
        }

        .task-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
        }

        .task-card.high-priority { border-left-color: #dc3545; }
        .task-card.urgent-priority { border-left-color: #fd7e14; }
        .task-card.medium-priority { border-left-color: #ffc107; }
        .task-card.low-priority { border-left-color: #28a745; }

        .task-title {
            font-weight: 600;
            margin-bottom: 8px;
            color: #333;
        }

        .task-meta {
            font-size: 12px;
            color: #666;
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
        }

        /* Eisenhower Matrix */
        .eisenhower-matrix {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            height: 500px;
        }

        .matrix-quadrant {
            border-radius: 15px;
            padding: 20px;
            position: relative;
        }

        .urgent-important { background: rgba(220, 53, 69, 0.1); border: 2px solid rgba(220, 53, 69, 0.3); }
        .urgent-not-important { background: rgba(255, 193, 7, 0.1); border: 2px solid rgba(255, 193, 7, 0.3); }
        .not-urgent-important { background: rgba(0, 123, 255, 0.1); border: 2px solid rgba(0, 123, 255, 0.3); }
        .not-urgent-not-important { background: rgba(108, 117, 125, 0.1); border: 2px solid rgba(108, 117, 125, 0.3); }

        .quadrant-title {
            font-weight: 600;
            margin-bottom: 15px;
            text-align: center;
            padding: 8px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.7);
        }

        /* Calendar Styles */
        .calendar-controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .calendar-nav {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .nav-btn {
            background: rgba(102, 126, 234, 0.1);
            border: none;
            padding: 8px 12px;
            border-radius: 10px;
            cursor: pointer;
            color: #667eea;
            transition: all 0.3s ease;
        }

        .nav-btn:hover {
            background: #667eea;
            color: white;
        }

        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 1px;
            background: #e9ecef;
            border-radius: 15px;
            overflow: hidden;
            margin-bottom: 20px;
        }

        .calendar-day {
            background: white;
            padding: 10px;
            min-height: 100px;
            position: relative;
        }

        .calendar-day.other-month {
            opacity: 0.3;
        }

        .calendar-day.today {
            background: rgba(102, 126, 234, 0.1);
        }

        .day-number {
            font-weight: 600;
            margin-bottom: 5px;
        }

        .day-header {
            background: #667eea;
            color: white;
            padding: 10px;
            text-align: center;
            font-weight: 600;
            min-height: auto;
        }

        .unassigned-tasks {
            background: rgba(248, 249, 250, 0.8);
            border-radius: 15px;
            padding: 20px;
            margin-top: 20px;
        }

        .unassigned-header {
            font-weight: 600;
            margin-bottom: 15px;
            color: #666;
        }

        /* Modal Styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(5px);
        }

        .modal-content {
            background: white;
            margin: 5% auto;
            padding: 30px;
            border-radius: 20px;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: #333;
        }

        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid rgba(102, 126, 234, 0.2);
            border-radius: 10px;
            font-size: 14px;
            transition: all 0.3s ease;
        }

        .form-group input:focus,
        .form-group select:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .form-actions {
            display: flex;
            gap: 10px;
            justify-content: flex-end;
            margin-top: 30px;
        }

        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.3s ease;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-secondary {
            background: rgba(108, 117, 125, 0.1);
            color: #6c757d;
        }

        .btn:hover {
            transform: translateY(-2px);
        }

        .close {
            color: #999;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            margin-top: -10px;
        }

        .close:hover {
            color: #333;
        }

        /* Drag and drop styles */
        .drag-over {
            background: rgba(102, 126, 234, 0.1) !important;
            border: 2px dashed #667eea !important;
        }

        .dragging {
            opacity: 0.5;
            transform: rotate(5deg);
        }

        @media (max-width: 768px) {
            .kanban-board {
                grid-template-columns: 1fr;
            }
            
            .eisenhower-matrix {
                grid-template-columns: 1fr;
                height: auto;
            }
            
            .calendar-grid {
                grid-template-columns: repeat(7, 1fr);
            }
            
            .calendar-day {
                min-height: 80px;
                padding: 5px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📅 Task Calendar</h1>
            <div class="tabs">
                <button class="tab active" onclick="showTab('tasks')">Tasks</button>
                <button class="tab" onclick="showTab('calendar')">Calendar</button>
            </div>
        </div>

        <div class="content">
            <!-- Tasks Tab -->
            <div id="tasks" class="tab-content active">
                <div class="view-toggle">
                    <button class="view-btn active" onclick="showTaskView('kanban')">Kanban Board</button>
                    <button class="view-btn" onclick="showTaskView('eisenhower')">Eisenhower Matrix</button>
                </div>
                
                <button class="add-task-btn" onclick="openTaskModal()">+ Add New Task</button>

                <!-- Kanban Board View -->
                <div id="kanban-view" class="task-view">
                    <div class="kanban-board">
                        <div class="kanban-column" data-status="todo">
                            <div class="kanban-header todo-header">To Do</div>
                            <div class="task-list" id="todo-tasks"></div>
                        </div>
                        <div class="kanban-column" data-status="in_progress">
                            <div class="kanban-header progress-header">In Progress</div>
                            <div class="task-list" id="progress-tasks"></div>
                        </div>
                        <div class="kanban-column" data-status="done">
                            <div class="kanban-header done-header">Done</div>
                            <div class="task-list" id="done-tasks"></div>
                        </div>
                    </div>
                </div>

                <!-- Eisenhower Matrix View -->
                <div id="eisenhower-view" class="task-view" style="display: none;">
                    <div class="eisenhower-matrix">
                        <div class="matrix-quadrant urgent-important" data-priority="urgent-important">
                            <div class="quadrant-title">Urgent & Important</div>
                            <div class="task-list" id="urgent-important-tasks"></div>
                        </div>
                        <div class="matrix-quadrant urgent-not-important" data-priority="urgent-not-important">
                            <div class="quadrant-title">Urgent & Not Important</div>
                            <div class="task-list" id="urgent-not-important-tasks"></div>
                        </div>
                        <div class="matrix-quadrant not-urgent-important" data-priority="not-urgent-important">
                            <div class="quadrant-title">Not Urgent & Important</div>
                            <div class="task-list" id="not-urgent-important-tasks"></div>
                        </div>
                        <div class="matrix-quadrant not-urgent-not-important" data-priority="not-urgent-not-important">
                            <div class="quadrant-title">Not Urgent & Not Important</div>
                            <div class="task-list" id="not-urgent-not-important-tasks"></div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Calendar Tab -->
            <div id="calendar" class="tab-content">
                <div class="calendar-controls">
                    <div class="view-toggle">
                        <button class="view-btn active" onclick="setCalendarView('month')">Month</button>
                        <button class="view-btn" onclick="setCalendarView('week')">Week</button>
                        <button class="view-btn" onclick="setCalendarView('day')">Day</button>
                    </div>
                    <div class="calendar-nav">
                        <button class="nav-btn" onclick="navigateCalendar(-1)">‹</button>
                        <span id="calendar-title">January 2024</span>
                        <button class="nav-btn" onclick="navigateCalendar(1)">›</button>
                        <button class="nav-btn" onclick="goToToday()">Today</button>
                    </div>
                </div>
                
                <div id="calendar-grid" class="calendar-grid"></div>
                
                <div class="unassigned-tasks">
                    <div class="unassigned-header">Unassigned Tasks</div>
                    <div id="unassigned-task-list"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Task Modal -->
    <div id="taskModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeTaskModal()">&times;</span>
            <h2 id="modal-title">Add New Task</h2>
            <form id="taskForm">
                <div class="form-group">
                    <label for="task-title">Title *</label>
                    <input type="text" id="task-title" required>
                </div>
                <div class="form-group">
                    <label for="task-description">Description</label>
                    <textarea id="task-description" rows="3"></textarea>
                </div>
                <div class="form-group">
                    <label for="task-due-date">Due Date</label>
                    <input type="date" id="task-due-date">
                </div>
                <div class="form-group">
                    <label for="task-assigned-date">Assigned Date</label>
                    <input type="date" id="task-assigned-date">
                </div>
                <div class="form-group">
                    <label for="task-priority">Priority</label>
                    <select id="task-priority">
                        <option value="low">Low</option>
                        <option value="medium" selected>Medium</option>
                        <option value="high">High</option>
                        <option value="urgent">Urgent</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="task-status">Status</label>
                    <select id="task-status">
                        <option value="todo" selected>To Do</option>
                        <option value="in_progress">In Progress</option>
                        <option value="done">Done</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="task-notes">Notes</label>
                    <textarea id="task-notes" rows="3"></textarea>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeTaskModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Save Task</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        let tasks = [];
        let currentDate = new Date();
        let calendarView = 'month';
        let editingTaskId = null;

        // Initialize the app
        document.addEventListener('DOMContentLoaded', function() {
            loadTasks();
            renderCalendar();
            setupDragAndDrop();
        });

        // Tab functionality
        function showTab(tabName) {
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            event.target.classList.add('active');
            
            // Update tab content
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            document.getElementById(tabName).classList.add('active');
            
            if (tabName === 'calendar') {
                renderCalendar();
            }
        }

        // Task view functionality
        function showTaskView(viewName) {
            document.querySelectorAll('.view-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            document.querySelectorAll('.task-view').forEach(view => view.style.display = 'none');
            document.getElementById(viewName + '-view').style.display = 'block';
            
            if (viewName === 'kanban') {
                renderKanbanBoard();
            } else if (viewName === 'eisenhower') {
                renderEisenhowerMatrix();
            }
        }

        // Calendar view functionality
        function setCalendarView(view) {
            calendarView = view;
            document.querySelectorAll('#calendar .view-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            renderCalendar();
        }

        // Load tasks from API
        async function loadTasks() {
            try {
                const response = await fetch('/api/tasks');
                tasks = await response.json();
                renderTasks();
            } catch (error) {
                console.error('Error loading tasks:', error);
            }
        }

        // Render tasks based on current view
        function renderTasks() {
            const activeView = document.querySelector('.task-view:not([style*="display: none"])');
            if (activeView && activeView.id === 'kanban-view') {
                renderKanbanBoard();
            } else if (activeView && activeView.id === 'eisenhower-view') {
                renderEisenhowerMatrix();
            }
        }

        // Render Kanban Board
        function renderKanbanBoard() {
            const todoList = document.getElementById('todo-tasks');
            const progressList = document.getElementById('progress-tasks');
            const doneList = document.getElementById('done-tasks');
            
            todoList.innerHTML = '';
            progressList.innerHTML = '';
            doneList.innerHTML = '';
            
            tasks.forEach(task => {
                const taskElement = createTaskCard(task);
                
                if (task.status === 'todo') {
                    todoList.appendChild(taskElement);
                } else if (task.status === 'in_progress') {
                    progressList.appendChild(taskElement);
                } else if (task.status === 'done') {
                    doneList.appendChild(taskElement);
                }
            });
        }

        // Render Eisenhower Matrix
        function renderEisenhowerMatrix() {
            const quadrants = {
                'urgent-important': document.getElementById('urgent-important-tasks'),
                'urgent-not-important': document.getElementById('urgent-not-important-tasks'),
                'not-urgent-important': document.getElementById('not-urgent-important-tasks'),
                'not-urgent-not-important': document.getElementById('not-urgent-not-important-tasks')
            };
            
            // Clear all quadrants
            Object.values(quadrants).forEach(quadrant => quadrant.innerHTML = '');
            
            tasks.forEach(task => {
                const taskElement = createTaskCard(task);
                const isUrgent = task.priority === 'urgent' || task.priority === 'high';
                const isImportant = task.priority === 'urgent' || task.priority === 'medium';
                
                let quadrantKey;
                if (isUrgent && isImportant) {
                    quadrantKey = 'urgent-important';
                } else if (isUrgent && !isImportant) {
                    quadrantKey = 'urgent-not-important';
                } else if (!isUrgent && isImportant) {
                    quadrantKey = 'not-urgent-important';
                } else {
                    quadrantKey = 'not-urgent-not-important';
                }
                
                quadrants[quadrantKey].appendChild(taskElement);
            });
        }

        // Create task card element
        function createTaskCard(task) {
            const card = document.createElement('div');
            card.className = `task-card ${task.priority}-priority`;
            card.draggable = true;
            card.dataset.taskId = task.id;
            
            const dueDate = task.due_date ? new Date(task.due_date).toLocaleDateString() : '';
            const assignedDate = task.assigned_date ? new Date(task.assigned_date).toLocaleDateString() : '';
            
            card.innerHTML = `
                <div class="task-title">${task.title}</div>
                <div class="task-description">${task.description}</div>
                <div class="task-meta">
                    <span>Due: ${dueDate || 'None'}</span>
                    <span>Assigned: ${assignedDate || 'None'}</span>
                </div>
            `;
            
            card.addEventListener('click', () => editTask(task.id));
            
            return card;
        }

        // Calendar functionality
        function renderCalendar() {
            const grid = document.getElementById('calendar-grid');
            const title = document.getElementById('calendar-title');
            
            if (calendarView === 'month') {
                renderMonthView(grid, title);
            } else if (calendarView === 'week') {
                renderWeekView(grid, title);
            } else if (calendarView === 'day') {
                renderDayView(grid, title);
            }
            
            renderUnassignedTasks();
        }

        function renderMonthView(grid, title) {
            const year = currentDate.getFullYear();
            const month = currentDate.getMonth();
            
            title.textContent = currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
            
            const firstDay = new Date(year, month, 1);
            const lastDay = new Date(year, month + 1, 0);
            const daysInMonth = lastDay.getDate();
            const startingDayOfWeek = firstDay.getDay();
            
            grid.innerHTML = '';
            
            // Add day headers
            const dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            dayHeaders.forEach(day => {
                const header = document.createElement('div');
                header.className = 'day-header';
                header.textContent = day;
                grid.appendChild(header);
            });
            
            // Add empty cells for days before month starts
            for (let i = 0; i < startingDayOfWeek; i++) {
                const emptyDay = document.createElement('div');
                emptyDay.className = 'calendar-day other-month';
                grid.appendChild(emptyDay);
            }
            
            // Add days of the month
            for (let day = 1; day <= daysInMonth; day++) {
                const dayElement = document.createElement('div');
                dayElement.className = 'calendar-day';
                
                const today = new Date();
                if (year === today.getFullYear() && month === today.getMonth() && day === today.getDate()) {
                    dayElement.classList.add('today');
                }
                
                const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                dayElement.dataset.date = dateStr;
                
                dayElement.innerHTML = `
                    <div class="day-number">${day}</div>
                    <div class="day-tasks"></div>
                `;
                
                // Add tasks for this day
                const dayTasks = tasks.filter(task => task.assigned_date === dateStr);
                const tasksContainer = dayElement.querySelector('.day-tasks');
                dayTasks.forEach(task => {
                    const taskElement = document.createElement('div');
                    taskElement.className = 'task-card mini';
                    taskElement.textContent = task.title;
                    taskElement.dataset.taskId = task.id;
                    taskElement.draggable = true;
                    tasksContainer.appendChild(taskElement);
                });
                
                grid.appendChild(dayElement);
            }
        }

        function renderWeekView(grid, title) {
            const startOfWeek = new Date(currentDate);
            startOfWeek.setDate(currentDate.getDate() - currentDate.getDay());
            
            const endOfWeek = new Date(startOfWeek);
            endOfWeek.setDate(startOfWeek.getDate() + 6);
            
            title.textContent = `${startOfWeek.toLocaleDateString()} - ${endOfWeek.toLocaleDateString()}`;
            
            grid.innerHTML = '';
            
            // Add day headers
            const dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            dayHeaders.forEach(day => {
                const header = document.createElement('div');
                header.className = 'day-header';
                header.textContent = day;
                grid.appendChild(header);
            });
            
            // Add days of the week
            for (let i = 0; i < 7; i++) {
                const day = new Date(startOfWeek);
                day.setDate(startOfWeek.getDate() + i);
                
                const dayElement = document.createElement('div');
                dayElement.className = 'calendar-day';
                
                const today = new Date();
                if (day.toDateString() === today.toDateString()) {
                    dayElement.classList.add('today');
                }
                
                const dateStr = day.toISOString().split('T')[0];
                dayElement.dataset.date = dateStr;
                
                dayElement.innerHTML = `
                    <div class="day-number">${day.getDate()}</div>
                    <div class="day-tasks"></div>
                `;
                
                // Add tasks for this day
                const dayTasks = tasks.filter(task => task.assigned_date === dateStr);
                const tasksContainer = dayElement.querySelector('.day-tasks');
                dayTasks.forEach(task => {
                    const taskElement = document.createElement('div');
                    taskElement.className = 'task-card mini';
                    taskElement.textContent = task.title;
                    taskElement.dataset.taskId = task.id;
                    taskElement.draggable = true;
                    tasksContainer.appendChild(taskElement);
                });
                
                grid.appendChild(dayElement);
            }
        }

        function renderDayView(grid, title) {
            title.textContent = currentDate.toLocaleDateString('en-US', { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
            });
            
            grid.innerHTML = '';
            grid.style.display = 'block';
            grid.style.gridTemplateColumns = '1fr';
            
            const dayElement = document.createElement('div');
            dayElement.className = 'calendar-day day-view';
            dayElement.style.minHeight = '400px';
            
            const today = new Date();
            if (currentDate.toDateString() === today.toDateString()) {
                dayElement.classList.add('today');
            }
            
            const dateStr = currentDate.toISOString().split('T')[0];
            dayElement.dataset.date = dateStr;
            
            dayElement.innerHTML = `
                <div class="day-number">${currentDate.getDate()}</div>
                <div class="day-tasks"></div>
            `;
            
            // Add tasks for this day
            const dayTasks = tasks.filter(task => task.assigned_date === dateStr);
            const tasksContainer = dayElement.querySelector('.day-tasks');
            dayTasks.forEach(task => {
                const taskElement = createTaskCard(task);
                tasksContainer.appendChild(taskElement);
            });
            
            grid.appendChild(dayElement);
        }

        function renderUnassignedTasks() {
            const container = document.getElementById('unassigned-task-list');
            container.innerHTML = '';
            
            const unassignedTasks = tasks.filter(task => !task.assigned_date);
            unassignedTasks.forEach(task => {
                const taskElement = createTaskCard(task);
                container.appendChild(taskElement);
            });
        }

        function navigateCalendar(direction) {
            if (calendarView === 'month') {
                currentDate.setMonth(currentDate.getMonth() + direction);
            } else if (calendarView === 'week') {
                currentDate.setDate(currentDate.getDate() + (direction * 7));
            } else if (calendarView === 'day') {
                currentDate.setDate(currentDate.getDate() + direction);
            }
            renderCalendar();
        }

        function goToToday() {
            currentDate = new Date();
            renderCalendar();
        }

        // Modal functionality
        function openTaskModal(taskId = null) {
            const modal = document.getElementById('taskModal');
            const title = document.getElementById('modal-title');
            const form = document.getElementById('taskForm');
            
            editingTaskId = taskId;
            
            if (taskId) {
                title.textContent = 'Edit Task';
                const task = tasks.find(t => t.id === taskId);
                if (task) {
                    document.getElementById('task-title').value = task.title;
                    document.getElementById('task-description').value = task.description || '';
                    document.getElementById('task-due-date').value = task.due_date || '';
                    document.getElementById('task-assigned-date').value = task.assigned_date || '';
                    document.getElementById('task-priority').value = task.priority;
                    document.getElementById('task-status').value = task.status;
                    document.getElementById('task-notes').value = task.notes || '';
                }
            } else {
                title.textContent = 'Add New Task';
                form.reset();
            }
            
            modal.style.display = 'block';
        }

        function closeTaskModal() {
            document.getElementById('taskModal').style.display = 'none';
            editingTaskId = null;
        }

        function editTask(taskId) {
            openTaskModal(taskId);
        }

        // Form submission
        document.getElementById('taskForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const taskData = {
                title: document.getElementById('task-title').value,
                description: document.getElementById('task-description').value,
                due_date: document.getElementById('task-due-date').value || null,
                assigned_date: document.getElementById('task-assigned-date').value || null,
                priority: document.getElementById('task-priority').value,
                status: document.getElementById('task-status').value,
                notes: document.getElementById('task-notes').value
            };
            
            try {
                let response;
                if (editingTaskId) {
                    response = await fetch(`/api/tasks/${editingTaskId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(taskData)
                    });
                } else {
                    response = await fetch('/api/tasks', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(taskData)
                    });
                }
                
                if (response.ok) {
                    closeTaskModal();
                    loadTasks();
                }
            } catch (error) {
                console.error('Error saving task:', error);
            }
        });

        // Drag and drop functionality
        function setupDragAndDrop() {
            let draggedElement = null;
            
            document.addEventListener('dragstart', function(e) {
                if (e.target.classList.contains('task-card')) {
                    draggedElement = e.target;
                    e.target.classList.add('dragging');
                }
            });
            
            document.addEventListener('dragend', function(e) {
                if (e.target.classList.contains('task-card')) {
                    e.target.classList.remove('dragging');
                    draggedElement = null;
                }
            });
            
            document.addEventListener('dragover', function(e) {
                e.preventDefault();
            });
            
            document.addEventListener('dragenter', function(e) {
                if (e.target.classList.contains('kanban-column') || 
                    e.target.classList.contains('matrix-quadrant') ||
                    e.target.classList.contains('calendar-day') ||
                    e.target.classList.contains('task-list')) {
                    e.target.classList.add('drag-over');
                }
            });
            
            document.addEventListener('dragleave', function(e) {
                if (e.target.classList.contains('drag-over')) {
                    e.target.classList.remove('drag-over');
                }
            });
            
            document.addEventListener('drop', function(e) {
                e.preventDefault();
                e.target.classList.remove('drag-over');
                
                if (!draggedElement) return;
                
                const taskId = parseInt(draggedElement.dataset.taskId);
                const task = tasks.find(t => t.id === taskId);
                
                if (!task) return;
                
                // Handle Kanban drops
                if (e.target.classList.contains('kanban-column') || e.target.closest('.kanban-column')) {
                    const column = e.target.classList.contains('kanban-column') ? 
                        e.target : e.target.closest('.kanban-column');
                    const status = column.dataset.status;
                    updateTaskStatus(taskId, status);
                }
                
                // Handle calendar drops
                else if (e.target.classList.contains('calendar-day') || e.target.closest('.calendar-day')) {
                    const dayElement = e.target.classList.contains('calendar-day') ? 
                        e.target : e.target.closest('.calendar-day');
                    const date = dayElement.dataset.date;
                    updateTaskDate(taskId, date);
                }
                
                // Handle unassigned area drops
                else if (e.target.closest('.unassigned-tasks')) {
                    updateTaskDate(taskId, null);
                }
            });
        }

        async function updateTaskStatus(taskId, status) {
            try {
                const response = await fetch(`/api/tasks/${taskId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: status })
                });
                
                if (response.ok) {
                    loadTasks();
                }
            } catch (error) {
                console.error('Error updating task status:', error);
            }
        }

        async function updateTaskDate(taskId, date) {
            try {
                const response = await fetch(`/api/tasks/${taskId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ assigned_date: date })
                });
                
                if (response.ok) {
                    loadTasks();
                    renderCalendar();
                }
            } catch (error) {
                console.error('Error updating task date:', error);
            }
        }

        // Close modal when clicking outside
        window.addEventListener('click', function(e) {
            const modal = document.getElementById('taskModal');
            if (e.target === modal) {
                closeTaskModal();
            }
        });

        // Initialize with some sample tasks
        async function initializeSampleTasks() {
            const sampleTasks = [
                {
                    title: "Complete project proposal",
                    description: "Write and submit the Q1 project proposal",
                    priority: "high",
                    status: "todo",
                    due_date: "2024-02-15"
                },
                {
                    title: "Team meeting",
                    description: "Weekly team sync meeting",
                    priority: "medium",
                    status: "todo",
                    assigned_date: new Date().toISOString().split('T')[0]
                },
                {
                    title: "Review code",
                    description: "Review pull requests from team members",
                    priority: "urgent",
                    status: "in_progress"
                }
            ];
            
            for (const task of sampleTasks) {
                try {
                    await fetch('/api/tasks', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(task)
                    });
                } catch (error) {
                    console.error('Error creating sample task:', error);
                }
            }
            
            loadTasks();
        }

        // Add some sample tasks on first load if no tasks exist
        setTimeout(() => {
            if (tasks.length === 0) {
                initializeSampleTasks();
            }
        }, 1000);
    </script>
</body>
</html>'''
    
    # Write the HTML template
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("Flask To-Do Calendar App created successfully!")
    print("\nTo run the app:")
    print("1. Install Flask: pip install flask")
    print("2. Run the app: python app.py")
    print("3. Open your browser to: http://localhost:5000")
    print("\nFeatures included:")
    print("- Tasks tab with Kanban board and Eisenhower matrix views")
    print("- Calendar tab with month/week/day views")
    print("- Drag and drop functionality")
    print("- Task management with notes, due dates, and assignments")
    print("- Modern, sleek design with transparency and rounded corners")
    
    app.run(debug=True)