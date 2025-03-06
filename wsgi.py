from app import app, socketio

application = socketio.WSGIApp(app)

if __name__ == '__main__':
    socketio.run(app) 