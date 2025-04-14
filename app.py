from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import time
from datetime import datetime
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# Store game rooms and their states
rooms = {}
coop_rooms = {}

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

@app.route('/coop')
def coop():
    return render_template('coop.html')

@app.route('/join_coop')
def join_coop():
    return render_template('join_coop.html')

def generate_grid(size, mines):
    grid = [[0 for _ in range(size)] for _ in range(size)]
    mine_positions = random.sample(range(size * size), mines)
    
    for pos in mine_positions:
        row = pos // size
        col = pos % size
        grid[row][col] = -1
        
        # Update adjacent cells
        for i in range(max(0, row-1), min(size, row+2)):
            for j in range(max(0, col-1), min(size, col+2)):
                if grid[i][j] != -1:
                    grid[i][j] += 1
                    
    return grid

@socketio.on('create_room')
def handle_create_room(data):
    room_id = data['room_id']
    player_name = data['player_name']
    grid_size = int(data['grid_size'])
    num_mines = int(data['num_mines'])
    
    if room_id in rooms:
        emit('error', {'message': 'Room already exists'})
        return
        
    rooms[room_id] = {
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

@socketio.on('create_coop_room')
def handle_create_coop_room(data):
    room_id = data['room_id']
    player_name = data['player_name']
    grid_size = int(data['grid_size'])
    num_mines = int(data['num_mines'])
    
    if room_id in coop_rooms:
        emit('error', {'message': 'Room already exists'})
        return
        
    grid = generate_grid(grid_size, num_mines)
    coop_rooms[room_id] = {
        'players': [player_name],
        'grid': grid,
        'grid_size': grid_size,
        'num_mines': num_mines,
        'revealed': [[False for _ in range(grid_size)] for _ in range(grid_size)],
        'flags': [[False for _ in range(grid_size)] for _ in range(grid_size)],
        'game_started': False,
        'game_over': False
    }
    
    join_room(room_id)
    emit('coop_room_created', {'players': coop_rooms[room_id]['players']}, room=room_id)

@socketio.on('join_room')
def handle_join_room(data):
    room_id = data['room_id']
    player_name = data['player_name']
    
    if room_id not in rooms:
        emit('error', {'message': 'Room not found'})
        return
        
    room = rooms[room_id]
    if len(room['players']) >= room['num_mines']:
        emit('error', {'message': 'Room is full'})
        return
        
    player_id = request.sid
    room['players'][player_id] = {
        'name': player_name,
        'game': MinesweeperGame(room['grid_size'], room['num_mines'])
    }
    
    join_room(room_id)
    emit('room_joined', {
        'room_id': room_id,
        'players': [p['name'] for p in room['players'].values()]
    })
    
    # Notify other players about the new player
    emit('player_joined', {
        'players': [p['name'] for p in room['players'].values()]
    }, room=room_id, include_self=False)
    
    # Send initial game state to the joining player
    send_game_state(room_id)

@socketio.on('join_coop_room')
def handle_join_coop_room(data):
    room_id = data['room_id']
    player_name = data['player_name']
    
    if room_id not in coop_rooms:
        emit('error', {'message': 'Room does not exist'})
        return
        
    if player_name in coop_rooms[room_id]['players']:
        emit('error', {'message': 'Name already taken'})
        return
        
    coop_rooms[room_id]['players'].append(player_name)
    
    join_room(room_id)
    emit('coop_room_joined', {'players': coop_rooms[room_id]['players']}, room=room_id)
    emit('player_joined_coop', {'players': coop_rooms[room_id]['players']}, room=room_id)

@socketio.on('start_game')
def handle_start_game(data):
    room_id = data['room_id']
    if room_id not in rooms:
        return
        
    room = rooms[room_id]
    room['started'] = True
    
    # Initialize games for all players
    for player_data in room['players'].values():
        player_data['game'] = MinesweeperGame(room['grid_size'], room['num_mines'])
    
    emit('game_start', room_id=room_id)

@socketio.on('start_coop_game')
def handle_start_coop_game(data):
    room_id = data['room_id']
    if room_id not in coop_rooms:
        return
        
    coop_room = coop_rooms[room_id]
    coop_room['game_started'] = True
    
    # Initialize the cooperative game grid
    grid_size = coop_room['grid_size']
    num_mines = coop_room['num_mines']
    grid = [[0 for _ in range(grid_size)] for _ in range(grid_size)]
    visible = [[False for _ in range(grid_size)] for _ in range(grid_size)]
    flagged = [[False for _ in range(grid_size)] for _ in range(grid_size)]
    
    # Place mines
    mines_placed = 0
    while mines_placed < num_mines:
        x = random.randint(0, grid_size - 1)
        y = random.randint(0, grid_size - 1)
        if grid[y][x] != -1:
            grid[y][x] = -1
            mines_placed += 1
            
            # Update adjacent cells
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    new_x, new_y = x + dx, y + dy
                    if 0 <= new_x < grid_size and 0 <= new_y < grid_size and grid[new_y][new_x] != -1:
                        grid[new_y][new_x] += 1
    
    coop_room['grid'] = grid
    coop_room['visible'] = visible
    coop_room['flagged'] = flagged
    coop_room['game_over'] = False
    
    emit('coop_game_started', {
        'grid': grid,
        'visible': visible,
        'flagged': flagged,
        'grid_size': grid_size
    }, room=room_id)

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

@socketio.on('reveal_coop_cell')
def handle_reveal_coop_cell(data):
    room_id = data['room_id']
    x = data['x']
    y = data['y']
    
    if room_id not in coop_rooms:
        return
        
    coop_room = coop_rooms[room_id]
    if not coop_room['game_started'] or coop_room['game_over']:
        return
        
    if coop_room['visible'][y][x] or coop_room['flagged'][y][x]:
        return
        
    coop_room['visible'][y][x] = True
    
    if coop_room['grid'][y][x] == -1:
        coop_room['game_over'] = True
        emit('coop_game_over', room=room_id)
        return
        
    if coop_room['grid'][y][x] == 0:
        # Reveal adjacent cells
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                new_x, new_y = x + dx, y + dy
                if 0 <= new_x < coop_room['grid_size'] and 0 <= new_y < coop_room['grid_size']:
                    if not coop_room['visible'][new_y][new_x] and not coop_room['flagged'][new_y][new_x]:
                        handle_reveal_coop_cell({
                            'room_id': room_id,
                            'x': new_x,
                            'y': new_y
                        })
    
    # Check if all non-mine cells are revealed
    all_revealed = True
    for y in range(coop_room['grid_size']):
        for x in range(coop_room['grid_size']):
            if coop_room['grid'][y][x] != -1 and not coop_room['visible'][y][x]:
                all_revealed = False
                break
        if not all_revealed:
            break
            
    if all_revealed:
        emit('coop_game_won', room=room_id)
    
    emit('coop_game_update', {
        'grid': coop_room['grid'],
        'visible': coop_room['visible'],
        'flagged': coop_room['flagged'],
        'game_over': coop_room['game_over']
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

@socketio.on('toggle_coop_flag')
def handle_toggle_coop_flag(data):
    room_id = data['room_id']
    x = data['x']
    y = data['y']
    
    if room_id not in coop_rooms:
        return
        
    coop_room = coop_rooms[room_id]
    if not coop_room['game_started'] or coop_room['game_over']:
        return
        
    if coop_room['visible'][y][x]:
        return
        
    coop_room['flagged'][y][x] = not coop_room['flagged'][y][x]
    
    emit('coop_game_update', {
        'grid': coop_room['grid'],
        'visible': coop_room['visible'],
        'flagged': coop_room['flagged'],
        'game_over': coop_room['game_over']
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

@socketio.on('new_coop_game')
def handle_new_coop_game(data):
    room_id = data['room_id']
    if room_id in coop_rooms:
        grid_size = coop_rooms[room_id]['grid_size']
        num_mines = coop_rooms[room_id]['num_mines']
        players = coop_rooms[room_id]['players']
        
        grid = generate_grid(grid_size, num_mines)
        coop_rooms[room_id] = {
            'players': players,
            'grid': grid,
            'grid_size': grid_size,
            'num_mines': num_mines,
            'revealed': [[False for _ in range(grid_size)] for _ in range(grid_size)],
            'flags': [[False for _ in range(grid_size)] for _ in range(grid_size)],
            'game_started': False,
            'game_over': False
        }
        
        emit('coop_game_reset', room=room_id)

@socketio.on('disconnect')
def handle_disconnect():
    for room_id, room in rooms.items():
        if request.sid in room['players']:
            del room['players'][request.sid]
            emit('player_left', {'players': [p['name'] for p in room['players'].values()]}, room=room_id)
            
    for room_id, room in coop_rooms.items():
        if request.sid in room.get('players', []):
            room['players'].remove(request.sid)
            emit('player_left_coop', {'players': room['players']}, room=room_id)

def send_game_state(room_id):
    if room_id not in rooms:
        return
        
    room = rooms[room_id]
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
    
    emit('game_update', {
        'grids': grids_data,
        'rankings': room['rankings']
    }, room=room_id)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True) 