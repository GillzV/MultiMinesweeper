from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import time
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Store game rooms and their states
rooms = {}

class MinesweeperGame:
    def __init__(self, size, num_mines):
        self.size = size
        self.num_mines = num_mines
        self.grid = [[0 for _ in range(size)] for _ in range(size)]
        self.visible = [[False for _ in range(size)] for _ in range(size)]
        self.flagged = [[False for _ in range(size)] for _ in range(size)]
        self.game_over = False
        self.won = False
        self.start_time = None
        self.end_time = None
        self.first_click = True

    def place_mines(self, first_x, first_y):
        # Clear the grid first
        self.grid = [[0 for _ in range(self.size)] for _ in range(self.size)]
        mines_placed = 0
        while mines_placed < self.num_mines:
            x = random.randint(0, self.size - 1)
            y = random.randint(0, self.size - 1)
            # Don't place mine at first click or in adjacent cells
            if (abs(x - first_x) > 1 or abs(y - first_y) > 1) and self.grid[y][x] != -1:
                self.grid[y][x] = -1
                mines_placed += 1
        self.calculate_numbers()

    def calculate_numbers(self):
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y][x] != -1:
                    count = 0
                    for dy in [-1, 0, 1]:
                        for dx in [-1, 0, 1]:
                            if dx == 0 and dy == 0:
                                continue
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

@socketio.on('create_room')
def handle_create_room(data):
    room_id = data['room_id']
    num_players = data['num_players']
    grid_size = data['grid_size']
    num_mines = data['num_mines']
    player_name = data['player_name']
    
    rooms[room_id] = {
        'num_players': num_players,
        'players': {},
        'grid_size': grid_size,
        'num_mines': num_mines,
        'started': False,
        'rankings': []
    }
    
    # Add the host as the first player
    player_id = request.sid
    rooms[room_id]['players'][player_id] = {
        'name': player_name,
        'game': MinesweeperGame(grid_size, num_mines)
    }
    
    join_room(room_id)
    emit('room_created', {'room_id': room_id})
    
    # Send initial game state to all players in the room
    send_game_state(room_id)

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

def send_game_state(room_id):
    room = rooms[room_id]
    grids_data = {}
    for pid, player_data in room['players'].items():
        grids_data[pid] = {
            'name': player_data['name'],
            'grid': player_data['game'].grid,
            'visible': player_data['game'].visible,
            'flagged': player_data['game'].flagged,
            'size': room['grid_size']
        }
    
    emit('game_update', {
        'grids': grids_data,
        'rankings': room['rankings']
    }, room=room_id)

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