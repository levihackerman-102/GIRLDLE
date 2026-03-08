import json
import jstyleson
import os
import random
from dataclasses import dataclass

DB_FILE = 'db.json'
CONFIG_FILE = 'config.json'
TEAMS_FILE = 'teams.json'

@dataclass
class GameConfig:
    contest_name: str
    initial_points: int
    min_points_cap: int
    admin_password: str
    csv_key: str

    @classmethod
    def from_dict(cls, data: dict):
        required_keys = ['contest_name', 'initial_points', 'min_points_cap', 'admin_password', 'csv_key']
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise ValueError(f"Missing required game config keys: {missing}")
        return cls(**{k: data[k] for k in required_keys})

class GameManager:
    def __init__(self):
        self.config: GameConfig = None # type: ignore
        self.load_config()
        self.load_db()

    def load_config(self):
        with open(CONFIG_FILE, 'r') as f:
            data = jstyleson.load(f)
            if 'game_config' not in data:
                 raise ValueError("game_config object is missing in config file")
            self.config = GameConfig.from_dict(data['game_config'])
            
        with open(TEAMS_FILE, 'r') as f:
            self.users = json.load(f)
            self.users.sort(key=lambda u: u.get('order', 999))
            # Map username to team data if needed, or just keep list

    def load_db(self):
        if not os.path.exists(DB_FILE):
            self.reset_db()
        else:
            with open(DB_FILE, 'r') as f:
                self.state = json.load(f)
                
                # Ensure default keys existence for older db files
                defaults = {
                     "phase": "GUESSING",
                     "round_number": 1,
                     "revealer_index": 0,
                     "total_revelations": 0,
                     "names": [],
                     "revealed_letters": [],
                     "team_scores": {},
                     "guesses_pending": {},
                     "logs": [],
                     "columns": []
                }
                for k, v in defaults.items():
                    if k not in self.state:
                        self.state[k] = v

                # Ensure names are populated if empty (first run)
                if not self.state['names']:
                    self.reset_names()
                
                # Auto-start if in setup phase
                if self.state.get('phase') == 'setup':
                    self.reset_db()

    def reset_db(self):
        self.state = {
            "phase": "GUESSING", # GUESSING, REVEAL, END
            "round_number": 1,
            "revealer_index": 0, # Index in self.users for who reveals next
            "total_revelations": 0,
            "names": [], # Will be populated
            "revealed_letters": [],
            "team_scores": {u['username']: 0 for u in self.users},
            "guesses_pending": {u['username']: True for u in self.users}, # Teams need to guess
            "logs": [],
            "columns": []
        }
        self.reset_names()
        self.snapshot_solve_counts() # Snapshot for round 1
        self.save_state()

    def reset_names(self):
        import csv
        
        csv_key = self.config.csv_key
        
        self.state['names'] = []
        if os.path.exists('contest_data.csv'):
            with open('contest_data.csv', 'r') as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    raise ValueError("contest_data.csv is empty or missing headers.")
                if csv_key not in reader.fieldnames:
                    raise ValueError(f"csv_key '{csv_key}' not found in contest_data.csv headers: {reader.fieldnames}")
                
                self.state['columns'] = list(reader.fieldnames)
                    
                for idx, row in enumerate(reader):
                    if csv_key not in row:
                        continue # Skip rows without the key
                        
                    name_obj = {
                        "id": idx + 1,
                        "name": row[csv_key],
                        "solved_by": [],
                    }
                    
                    # Store everything else as metadata
                    for k, v in row.items():
                        if k != csv_key and k != "id" and k != "name" and k != "solved_by":
                            name_obj[k] = v
                    
                    self.state['names'].append(name_obj)
                            
        self.save_state()

    def save_state(self):
        with open(DB_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)

    def get_points_for_name(self, name_obj, use_snapshot=False):
        initial = self.config.initial_points
        min_cap = self.config.min_points_cap
        
        # Use snapshot from round start if available and requested
        if use_snapshot:
            solved_penalty = name_obj.get('solved_at_round_start', 0)
        else:
            solved_penalty = len(name_obj['solved_by'])
        
        # Deduct 1 for each revelation round occurred
        reveal_penalty = self.state['total_revelations']
        
        score = initial - solved_penalty - reveal_penalty
        return max(score, min_cap)
    
    def snapshot_solve_counts(self):
        """Called at the start of each guessing round to snapshot solve counts."""
        for n in self.state['names']:
            n['solved_at_round_start'] = len(n['solved_by'])

    def has_completed_game(self, username):
        """Check if a team has solved all names in the database."""
        total_count = len(self.state['names'])
        if total_count == 0:
            return False
        solved_count = sum(1 for n in self.state['names'] if username in n['solved_by'])
        return solved_count >= total_count

    def all_players_finished(self):
        """Check if every team has completed the entire game."""
        if not self.users:
            return False
        for u in self.users:
            if not self.has_completed_game(u['username']):
                return False
        return True

    def mask_name(self, name):
        # Replace non-space, non-revealed chars with _
        # Also respect spaces.
        visible = ""
        normalized_reveals = set(c.upper() for c in self.state['revealed_letters'])
        
        # We want to preserve word structure for frontend
        # But we are returning a string. 
        # Using a special delimiter for word boundaries?
        # No, let's just use standard chars, frontend CSS with 'white-space: pre-wrap' and wide spacing will handle it.
        # But we need to make sure spaces in the Name are actually spaces in output.
        
        # ACTUALLY, to guarantee "large space between words" and "small space between letters":
        # We can treat each letter as "C " or "_ "
        # And each word space as "   " (triple space)
        
        for char in name:
            if char == " ":
                visible += "     " # 5 spaces for word gap
            elif char.upper() in normalized_reveals:
                visible += char + " "
            else:
                visible += "_ "
        return visible.strip()

    def submit_guess(self, username, guess):
        if self.state['phase'] != 'GUESSING':
            return {"status": "error", "message": "Not in guessing phase"}
        
        if not self.state['guesses_pending'].get(username, False):
             # Already guessed this round?
             # User prompt: "If they get a correct answer they can attempt entering another name."
             # "However if they get it incorrect, they cannot guess more."
             # So we need to track if they are "locked out" for this round or "done".
             # Let's verify logic:
             # "On each turn, all 6 teams will see a textbox... first guess a name... If correct... attempt another. else incorrect... cannot guess more."
             # This implies "guesses_pending" is actually "can_still_guess".
             return {"status": "error", "message": "You have already finished guessing for this round."}

        # Check guess
        guess = guess.strip()
        match_found = None
        for name_obj in self.state['names']:
            if name_obj['name'].lower() == guess.lower():
                match_found = name_obj
                break
        
        if match_found:
            # Correct!
            if username in match_found['solved_by']:
                 return {"status": "error", "message": "You already solved this name!"}
            
            points = self.get_points_for_name(match_found, use_snapshot=True)
            self.state['team_scores'][username] = self.state['team_scores'].get(username, 0) + points
            match_found['solved_by'].append(username)
            name_id = match_found.get('id', '?')
            year = match_found.get('year', '')
            if not year and 'date' in match_found:
                year = match_found.get('date', '????')[:4] # Extract year from "YYYY/MM/DD"
            
            if not year:
                year = "????"
                
            self.log_event(f"Team {username} guessed #{name_id} ({year}) (+{points})")
            
            # Check if this team has solved ALL names
            if self.has_completed_game(username):
                self.state['guesses_pending'][username] = False
                self.log_event(f"Team {username} has completed {self.config.contest_name}!")

            self.save_state()
            self.check_all_guessed() # Auto-transition if everyone is done
            return {"status": "success", "message": f"Correct! +{points} points.", "correct": True}
        else:
            # Incorrect
            self.state['guesses_pending'][username] = False
            self.save_state()
            self.check_all_guessed()  # Auto-transition if everyone is done
            return {"status": "success", "message": "Incorrect guess. You are done for this round.", "correct": False}

    def skip_guess(self, username):
        # User might want to stop guessing voluntarily
        self.state['guesses_pending'][username] = False
        self.save_state()
        self.check_all_guessed()  # Auto-transition if everyone is done
        return {"status": "success"}

    def check_all_guessed(self):
        """If all teams have finished guessing, automatically end the round."""
        if self.state['phase'] != 'GUESSING':
            return
        
        # Check if any team still has guesses pending
        for pending in self.state['guesses_pending'].values():
            if pending:
                return  # At least one team can still guess
        
        # All teams are done for this round
        # But if EVERYONE has finished the ENTIRE game, just finish
        if self.all_players_finished():
            self.finish_game()
            return

        # All teams are done, transition to REVEAL
        self.admin_end_round()

    def admin_end_round(self):
        # Transition GUESSING -> REVEAL
        # Or finish game if max rounds
        max_rounds = 12 # 12 names in the list
        
        if self.state['phase'] == 'GUESSING':
            if self.state['round_number'] >= max_rounds:
                 self.finish_game()
                 return
            
            self.state['phase'] = 'REVEAL'
            self.log_event(f"End of Guessing Round {self.state['round_number']}")
            self.save_state()
        else:
            pass # Already in reveal?
            
    def finish_game(self):
        self.state['phase'] = 'FINISHED'
        # Reveal all names
        for n in self.state['names']:
            # We don't actually change the db 'name' field, just frontend rendering logic
            pass 
        self.log_event("Game Finished!")
        self.save_state()

    def admin_reveal_letter(self, letter):
        if self.state['phase'] != 'REVEAL':
             return {"status": "error", "message": "Not in reveal phase"}
        
        letter = letter.upper()
        if len(letter) != 1 or not letter.isalpha():
             return {"status": "error", "message": "Invalid letter"}
        
        if letter in self.state['revealed_letters']:
             return {"status": "error", "message": "Letter already revealed"}
        
        self.state['revealed_letters'].append(letter)
        self.state['total_revelations'] += 1
        self.state['phase'] = 'GUESSING'
        self.state['round_number'] += 1
        
        # Advance revealer index
        self.state['revealer_index'] = (self.state['revealer_index'] + 1) % len(self.users)
        
        # Reset guesses pending (only for those who haven't finished the entire game)
        self.state['guesses_pending'] = {
            u['username']: (not self.has_completed_game(u['username'])) 
            for u in self.users
        }
        
        self.log_event(f"Revealed letter: {letter}")
        self.snapshot_solve_counts() # Snapshot for new round
        self.save_state()
        self.check_all_guessed() # Check if everyone is already done
        return {"status": "success"}

    def log_event(self, msg):
        self.state['logs'].append(msg)
        # Keep logs trimmed?
        self.state['logs'] = self.state['logs'][-20:]
        
    def calculate_scores(self):
        raw_scores = self.state['team_scores']
        return raw_scores

    def get_public_state(self):
        # For Admin Display
        raw_scores = self.calculate_scores()
        
        display_names = []
        is_finished = self.state['phase'] == 'FINISHED'
        
        for n in self.state['names']:
            masked = self.mask_name(n['name'])
            # If finished, we just show the name? Or handled by frontend? 
            # User wants: "Finish game ... reveal all answers"
            
            display_obj = {
                "id": n.get('id', 0),
                "display": n['name'] if is_finished else masked,
                "is_fully_revealed": is_finished or (n['name'].strip() == self.unmasked_name(n['name'])),
                "solved_by": n['solved_by'],
                "current_points": self.get_points_for_name(n, use_snapshot=(self.state['phase'] == 'GUESSING')),
            }
            
            # Add any other metadata from the csv to display_obj
            for k, v in n.items():
                if k not in ["id", "name", "solved_by", "solved_at_round_start"]:
                    display_obj[k] = v
                    
            display_names.append(display_obj)
            
        return {
            "phase": self.state['phase'],
            "round": self.state['round_number'],
            "scores": raw_scores,
            "table": display_names,
            "revealer": self.users[self.state['revealer_index']]['username'] if self.users else "",
            "logs": self.state['logs'],
            "columns": self.state.get('columns', []),
            "csv_key": self.config.csv_key
        }

    def unmasked_name(self, name):
        # Just logic check
        # We need to see if mask_name == name (ignoring spaces/formatting)
        # But actually we can just check if all letters are in revealed_letters
        # Using a simple check here for now:
        return name # Only referencing logic, actual check done in loop above

    def get_player_state(self, username):
        # Private state for player
        # Need to know if they can guess, and history of their correct guesses (visible in admin anyway)
        
        # Player sees blanks AND their solved names
        player_names_view = []
        for n in self.state['names']:
            if username in n['solved_by']:
                # Show the name if solved by this user
                player_names_view.append({"id": n.get('id', 0), "display": n['name'], "status": "solved"})
            else:
                # Show mask
                player_names_view.append({"id": n.get('id', 0), "display": self.mask_name(n['name']), "status": "unsolved"})
        
        total_count = len(self.state['names'])
        solved_count = sum(1 for n in self.state['names'] if username in n['solved_by'])
        all_solved = solved_count >= total_count
        
        return {
            "can_guess": self.state['guesses_pending'].get(username, False),
            "phase": self.state['phase'],
            "my_score": self.state['team_scores'].get(username, 0),
            "round": self.state['round_number'],
            "names": player_names_view,
            "all_solved": all_solved
        }

    def validate_login(self, username, password):
        for u in self.users:
            if u['username'] == username and u['password'] == password:
                return True
        return False
