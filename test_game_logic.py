import unittest
import json
import os
from game_manager import GameManager

# Setup dummy config for testing
TEST_CONFIG = {
    "game_config": {
        "initial_points": 12,
        "normalized_max_score": 60,
        "min_points_cap": 1,
        "admin_password": "test"
    },
    "users": [
        {"username": "p1", "password": "1", "ranking": 1},
        {"username": "p2", "password": "1", "ranking": 2}
    ]
}

class TestGameLogic(unittest.TestCase):
    def setUp(self):
        # Write test config and db
        with open('config_test.json', 'w') as f:
            json.dump(TEST_CONFIG, f)
        
        if os.path.exists('db_test.json'):
            os.remove('db_test.json')

        # Patch constants in game_manager via simple string replace implementation locally
        # or just modify the class instance if possible.
        # Since I can't import properly with different constants without modifying the file,
        # I will assume the prompt allows me to run this by temporarily modifying the file or 
        # I'll just rely on the fact that I can instantiate GameManager and maybe swap constants if they were class vars.
        # But they are global vars in game_manager.
        
        # ACTUALLY: I will just overwrite config.json for the test and backup the old one.
        if os.path.exists('config.json'):
            os.rename('config.json', 'config.json.bak')
        with open('config.json', 'w') as f:
            json.dump(TEST_CONFIG, f)
            
        if os.path.exists('db.json'):
            os.rename('db.json', 'db.json.bak')

        self.gm = GameManager()

    def tearDown(self):
        # Restore files
        if os.path.exists('config.json.bak'):
            os.replace('config.json.bak', 'config.json')
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
        # Should be 11 points (1 previous solve)
        self.assertIn("11", res['message']) 
        
        self.assertEqual(self.gm.state['team_scores']['p2'], 11)

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
