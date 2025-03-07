from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import time
from datetime import datetime
import os
import logging
from collections import defaultdict

# Set up logging with less verbose output
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
app.config['JSON_SORT_KEYS'] = False  # Prevent JSON key sorting for better performance
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 86400  # Cache static files for 1 day

# Configure SocketIO for better performance
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1024 * 1024,  # 1MB buffer size
    manage_session=False  # Disable session handling for better performance
)

# Use a more efficient data structure for rooms
rooms = defaultdict(dict)

class MinesweeperGame:
    def __init__(self, size, num_mines):
        self.size = size
        self.num_mines = num_mines
        # Use list comprehension for better performance
        self.grid = [[0] * size for _ in range(size)]
        self.visible = [[False] * size for _ in range(size)]
        self.flagged = [[False] * size for _ in range(size)]
        self.game_over = False
        self.won = False
        self.start_time = None
        self.end_time = None
        self.first_click = True
        self._adjacent_cells = list(self._generate_adjacent_cells())

    def _generate_adjacent_cells(self):
        # Pre-calculate adjacent cell offsets
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                yield (dx, dy)

    def place_mines(self, first_x, first_y):
        self.grid = [[0] * self.size for _ in range(self.size)]
        # Pre-calculate valid positions for mines
        valid_positions = [
            (x, y) for x in range(self.size) for y in range(self.size)
            if abs(x - first_x) > 1 or abs(y - first_y) > 1
        ]
        # Place mines randomly using sample
        mine_positions = random.sample(valid_positions, min(self.num_mines, len(valid_positions)))
        for x, y in mine_positions:
            self.grid[y][x] = -1
        self.calculate_numbers()

    def calculate_numbers(self):
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y][x] != -1:
                    count = 0
                    for dx, dy in self._adjacent_cells:
                        new_x, new_y = x + dx, y + dy
                        if 0 <= new_x < self.size and 0 <= new_y < self.size:
                            if self.grid[new_y][new_x] == -1:
                                count += 1
                    self.grid[y][x] = count

    def reveal(self, x, y):
        if not self.start_time:
            self.start_time = time.time()
        if self.visible[y][x] or self.flagged[y][x]:
            return
            
        # If this is the first click, place mines now
        if self.first_click:
            self.place_mines(x, y)
            self.first_click = False
            
        self.visible[y][x] = True
        if self.grid[y][x] == -1:
            self.game_over = True
            self.end_time = time.time()
            return
        if self.grid[y][x] == 0:
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    new_x, new_y = x + dx, y + dy
                    if 0 <= new_x < self.size and 0 <= new_y < self.size:
                        self.reveal(new_x, new_y)
        if self.check_win():
            self.won = True
            self.end_time = time.time()

    def toggle_flag(self, x, y):
        if not self.visible[y][x]:
            self.flagged[y][x] = not self.flagged[y][x]
            if self.check_win():
                self.won = True
                self.end_time = time.time()

    def check_win(self):
        # Check if all mines are flagged and all non-mines are revealed
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y][x] == -1 and not self.flagged[y][x]:
                    return False
                if self.grid[y][x] != -1 and not self.visible[y][x]:
                    return False
        return True

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/host')
def host():
    return render_template('host.html')

@app.route('/join')
def join():
    return render_template('join.html')

def send_game_state(room_id):
    """Optimized game state sender"""
    try:
        room = rooms[room_id]
        # Create a more efficient data structure for grid data
        grids_data = {
            pid: {
                'name': pdata['name'],
                'grid': pdata['game'].grid,
                'visible': pdata['game'].visible,
                'flagged': pdata['game'].flagged,
                'size': room['grid_size']
            }
            for pid, pdata in room['players'].items()
        }
        
        emit('game_update', {
            'grids': grids_data,
            'rankings': room.get('rankings', [])
        }, room=room_id)
    except Exception as e:
        logger.error(f"Error sending game state: {str(e)}")

@socketio.on('create_room')
def handle_create_room(data):
    try:
        room_id = data['room_id']
        rooms[room_id] = {
            'num_players': data['num_players'],
            'players': {},
            'grid_size': data['grid_size'],
            'num_mines': data['num_mines'],
            'started': False,
            'rankings': []
        }
        
        player_id = request.sid
        rooms[room_id]['players'][player_id] = {
            'name': data['player_name'],
            'game': MinesweeperGame(data['grid_size'], data['num_mines'])
        }
        
        join_room(room_id)
        emit('room_created', {'room_id': room_id})
        send_game_state(room_id)
    except Exception as e:
        logger.error(f"Error creating room: {str(e)}")
        emit('error', {'message': str(e)})

@socketio.on('join_room')
def handle_join_room(data):
    room_id = data['room_id']
    player_name = data['player_name']
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
    
    room = rooms[room_id]
    if len(room['players']) >= room['num_players']:
        emit('error', {'message': 'Room is full'})
        return
    
    player_id = request.sid
    room['players'][player_id] = {
        'name': player_name,
        'game': MinesweeperGame(room['grid_size'], room['num_mines'])
    }
    
    join_room(room_id)
    emit('joined_room', {'room_id': room_id})
    
    # Send game state to all players in the room
    send_game_state(room_id)

@socketio.on('start_game')
def handle_start_game(data):
    room_id = data['room_id']
    if room_id in rooms:
        room = rooms[room_id]
        room['started'] = True
        emit('game_started', room_id=room_id)

@socketio.on('reveal_cell')
def handle_reveal_cell(data):
    room_id = data['room_id']
    x = data['x']
    y = data['y']
    
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    if not room['started']:
        return
    
    player_id = request.sid
    if player_id not in room['players']:
        return
    
    player = room['players'][player_id]
    game = player['game']
    
    # Don't allow moves if the player has already lost
    if game.game_over:
        return
    
    game.reveal(x, y)
    
    # Update game state for all players
    grids_data = {}
    for pid, player_data in room['players'].items():
        grids_data[pid] = {
            'name': player_data['name'],
            'grid': player_data['game'].grid,
            'visible': player_data['game'].visible,
            'flagged': player_data['game'].flagged,
            'size': room['grid_size'],
            'game_over': player_data['game'].game_over
        }
    
    if game.game_over or game.won:
        if game.won:
            completion_time = game.end_time - game.start_time
            room['rankings'].append({
                'name': player['name'],
                'time': completion_time,
                'status': 'completed'
            })
        elif game.game_over:
            room['rankings'].append({
                'name': player['name'],
                'time': None,
                'status': 'dnf'
            })
        room['rankings'].sort(key=lambda x: (x['status'] == 'dnf', x['time'] if x['time'] is not None else float('inf')))
    
    emit('game_update', {
        'grids': grids_data,
        'game_over': game.game_over,
        'won': game.won,
        'rankings': room['rankings'],
        'loser_id': player_id if game.game_over else None
    }, room=room_id)

@socketio.on('toggle_flag')
def handle_toggle_flag(data):
    room_id = data['room_id']
    x = data['x']
    y = data['y']
    
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    if not room['started']:
        return
    
    player_id = request.sid
    if player_id not in room['players']:
        return
    
    player = room['players'][player_id]
    game = player['game']
    
    # Don't allow moves if the player has already lost
    if game.game_over:
        return
    
    game.toggle_flag(x, y)
    
    # Update game state for all players
    grids_data = {}
    for pid, player_data in room['players'].items():
        grids_data[pid] = {
            'name': player_data['name'],
            'grid': player_data['game'].grid,
            'visible': player_data['game'].visible,
            'flagged': player_data['game'].flagged,
            'size': room['grid_size'],
            'game_over': player_data['game'].game_over
        }
    
    if game.won:
        completion_time = game.end_time - game.start_time
        room['rankings'].append({
            'name': player['name'],
            'time': completion_time,
            'status': 'completed'
        })
        room['rankings'].sort(key=lambda x: (x['status'] == 'dnf', x['time'] if x['time'] is not None else float('inf')))
    
    emit('game_update', {
        'grids': grids_data,
        'game_over': game.game_over,
        'won': game.won,
        'rankings': room['rankings'],
        'loser_id': player_id if game.game_over else None
    }, room=room_id)

@socketio.on('new_game')
def handle_new_game(data):
    room_id = data['room_id']
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    room['started'] = False
    room['rankings'] = []
    
    # Reset all players' games
    for player_id, player_data in room['players'].items():
        player_data['game'] = MinesweeperGame(room['grid_size'], room['num_mines'])
    
    # Send initial game state to all players
    send_game_state(room_id)
    emit('game_reset', room_id=room_id)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port) 