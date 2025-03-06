from app import app, socketio

# Create WSGI app
application = socketio.middleware(app)

if __name__ == '__main__':
    socketio.run(app) 