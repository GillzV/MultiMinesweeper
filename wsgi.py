from app import app, socketio

# Create the WSGI application
application = socketio.middleware(app)

if __name__ == '__main__':
    socketio.run(app) 