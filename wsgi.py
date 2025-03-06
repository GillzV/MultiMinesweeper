from gevent import monkey
monkey.patch_all()

from app import app, socketio

app = socketio.WSGIApp(app)

if __name__ == '__main__':
    socketio.run(app) 