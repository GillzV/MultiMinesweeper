from gevent import monkey
monkey.patch_all()

from app import app, socketio

application = socketio.WSGIApp(app)
app = application

if __name__ == '__main__':
    socketio.run(app) 