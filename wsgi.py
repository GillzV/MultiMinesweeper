import eventlet
eventlet.monkey_patch()

from app import app, socketio

# Wrap Flask app with SocketIO's middleware
application = socketio.wsgi_app(app)

if __name__ == '__main__':
    socketio.run(app) 