import unittest
import json
import os
from game_manager import GameManager

# Setup dummy config for testing
TEST_CONFIG = {
    "game_config": {
        "initial_points": 12,
        "min_points_cap": 1,
        "admin_password": "test",
        "csv_key": "girl"
    }
}

TEST_TEAMS = [
    {"username": "p1", "password": "1", "rank": 1},
    {"username": "p2", "password": "1", "rank": 2}
]

TEST_CSV = [
    "girl,year",
    '"Kurisu Makise",2014',
    '"Rem",2018'
]

class TestGameLogic(unittest.TestCase):
    def setUp(self):
        # Write test config, db and csv
        with open('config_test.json', 'w') as f:
            json.dump(TEST_CONFIG, f)
        
        if os.path.exists('db_test.json'):
            os.remove('db_test.json')

        # Backup and overwrite files for testing
        if os.path.exists('config.json'):
            os.rename('config.json', 'config.json.bak')
        with open('config.json', 'w') as f:
            json.dump(TEST_CONFIG, f)

        if os.path.exists('teams.json'):
            os.rename('teams.json', 'teams.json.bak')
        with open('teams.json', 'w') as f:
            json.dump(TEST_TEAMS, f)
            
        if os.path.exists('contest_data.csv'):
            os.rename('contest_data.csv', 'contest_data.csv.bak')
        with open('contest_data.csv', 'w') as f:
            f.write("\n".join(TEST_CSV))
            
        if os.path.exists('db.json'):
            os.rename('db.json', 'db.json.bak')

        self.gm = GameManager()

    def tearDown(self):
        # Restore files
        if os.path.exists('config.json.bak'):
            os.replace('config.json.bak', 'config.json')
        if os.path.exists('teams.json.bak'):
            os.replace('teams.json.bak', 'teams.json')
        if os.path.exists('contest_data.csv.bak'):
            os.replace('contest_data.csv.bak', 'contest_data.csv')
        elif os.path.exists('contest_data.csv'):
            os.remove('contest_data.csv')
        if os.path.exists('db.json.bak'):
            os.replace('db.json.bak', 'db.json')
            
    def test_guessing_points(self):
        # Round 1
        name = "Kurisu Makise"
        
        # Player 1 guesses correctly
        res = self.gm.submit_guess("p1", "kurisu makise") # Case insensitive
        self.assertTrue(res['correct'])
        self.assertIn("12", res['message']) # 12 points
        
        # Verify score
        self.assertEqual(self.gm.state['team_scores']['p1'], 12)
        
        # Player 2 guesses same name
        res = self.gm.submit_guess("p2", "Kurisu Makise")
        self.assertTrue(res['correct'])
        # Should be 12 points
        self.assertIn("12", res['message']) 
        
        self.assertEqual(self.gm.state['team_scores']['p2'], 12)

    def test_reveal_penalty(self):
        name = "Rem"
        # Reveal a letter 'R'
        self.gm.state['phase'] = 'REVEAL'
        self.gm.admin_reveal_letter('R')
        
        # Back to guessing
        self.gm.state['phase'] = 'GUESSING' # Logic handles this auto but let's be sure
        
        # Player 1 guesses Rem
        res = self.gm.submit_guess("p1", "rem")
        # Base 12 - 0 solved - 1 reveal = 11
        self.assertTrue(res['correct'])
        self.assertIn("11", res['message'])
        
    def test_min_cap(self):
        # Force huge penalty
        self.gm.state['total_revelations'] = 20
        res = self.gm.submit_guess("p1", "rem")
        # Should be capped at 1
        self.assertIn("1", res['message'])
        self.assertNotIn("-", res['message']) 

    def test_wrong_guess_lockout(self):
        res = self.gm.submit_guess("p1", "WrongName")
        self.assertFalse(res['correct'])
        self.assertFalse(self.gm.state['guesses_pending']['p1'])
        
        # Try guessing again
        res2 = self.gm.submit_guess("p1", "OtherName")
        self.assertEqual(res2['status'], "error")

if __name__ == '__main__':
    unittest.main()
