from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from game_manager import GameManager
import os

from datetime import timedelta

app = Flask(__name__)
# Use a static secret key so sessions survive server restarts
app.secret_key = "super_secret_anime_key_detective"
app.permanent_session_lifetime = timedelta(days=365)
gm = GameManager()

# --- Routes ---

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('player_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Check Player Login
        if gm.validate_login(username, password):
            session.permanent = True
            session['user'] = username
            session['role'] = 'player'
            return redirect(url_for('player_dashboard'))
        
        # Check Admin Login
        admin_pass = gm.config.get('admin_password', 'admin')
        if username == 'admin' and password == admin_pass:
            session.permanent = True
            session['user'] = 'admin'
            session['role'] = 'admin'
            return redirect(url_for('admin_dashboard'))
            
        return render_template('login.html', error="Invalid credentials")
        
    return render_template('login.html')

@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/play')
def player_dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('player.html', user=session['user'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- API ---

@app.route('/api/state')
def get_state():
    # Public state for everyone (admin view essentially)
    return jsonify(gm.get_public_state())

@app.route('/api/player_state')
def get_player_state():
    if 'user' not in session:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(gm.get_player_state(session['user']))

@app.route('/api/guess', methods=['POST'])
def guess():
    if 'user' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    data = request.json
    guess_text = data.get('guess')
    if not guess_text:
        # Assume "Pass" / Stop guessing
        gm.skip_guess(session['user'])
        return jsonify({"status": "success", "message": "You passed for this round."})
        
    result = gm.submit_guess(session['user'], guess_text)
    return jsonify(result)

@app.route('/api/admin/end_round', methods=['POST'])
def end_round():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    gm.admin_end_round()
    return jsonify({"status": "success"})

@app.route('/api/admin/finish', methods=['POST'])
def finish_game():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    gm.finish_game()
    return jsonify({"status": "success"})

@app.route('/api/admin/reveal', methods=['POST'])
def reveal():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    data = request.json
    letter = data.get('letter')
    if not letter:
        return jsonify({"status": "error", "message": "Missing letter"})
        
    result = gm.admin_reveal_letter(letter)
    return jsonify(result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
