from flask import Flask

app = Flask(__name__)

@app.route('/vk')
def vk_handler():
    return "VK Handler"

if __name__ == '__main__':
    app.run()