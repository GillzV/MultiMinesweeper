from app import app, socketio

# Create WSGI app
application = socketio.wrap_app(app)

if __name__ == '__main__':
    socketio.run(app) 