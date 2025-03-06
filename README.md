# Multiplayer Minesweeper

A multiplayer version of the classic Minesweeper game where multiple players can compete simultaneously on different grids.

## Features

- Multiple players can play simultaneously
- Each player gets their own unique grid
- Real-time updates of all players' progress
- Rankings based on completion time
- Adjustable grid size and number of mines
- Shareable room links for easy joining
- Custom player names

## Setup

1. Make sure you have Python 3.7+ installed
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python app.py
   ```
4. Open your web browser and navigate to `http://localhost:5000`

## How to Play

1. **Hosting a Game:**
   - Click "Host a Game" on the main page
   - Select the number of players (2-5)
   - Choose the grid size (3x3 to 8x8)
   - Select the number of mines
   - Click "Create Room"
   - Share the generated link with your friends

2. **Joining a Game:**
   - Click "Join a Game" on the main page
   - Enter your name
   - Enter the room code (or use the shared link)
   - Click "Join Game"

3. **Playing:**
   - Your grid will be displayed larger than others
   - Click on cells to reveal them
   - Numbers indicate how many mines are adjacent to each cell
   - Avoid clicking on mines
   - Complete your grid to get a ranking
   - Watch other players' progress in the background

## Game Rules

- Each player gets their own unique grid
- Numbers in cells indicate how many mines are adjacent to that cell
- Clicking a mine ends your game
- Revealing all non-mine cells wins the game
- Players are ranked based on their completion time
- The game ends for all players when the last player finishes 