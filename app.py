import random
from flask import Flask

app = Flask(__name__)

@app.route('/')
def roll():
    die1 = random.randint(1, 6)
    die2 = random.randint(1, 6)
    total = die1 + die2
    if total in (7, 11):
        outcome = "Natural — you win!"
    elif total in (2, 3, 12):
        outcome = "Craps — you lose!"
    else:
        outcome = f"Point is {total}"
    return {"die1": die1, "die2": die2, "total": total, "outcome": outcome}

@app.route('/health')
def health():
    return {"status": "healthy"}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)