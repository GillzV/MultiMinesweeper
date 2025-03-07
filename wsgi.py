from app import app, socketio

# Create the WSGI application
application = app

if __name__ == '__main__':
    socketio.run(app) 