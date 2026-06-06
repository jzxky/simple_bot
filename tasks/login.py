"""
Handles initial login and automatic session re-login.
"""

from tasks.base import Task, Action
from state import GameState

LOGIN_URL = "https://mafiamatrix.com/default.asp"
LOGGED_IN_URL = "https://mafiamatrix.com/loggedin.asp"
PLAY_URL = "https://mafiamatrix.com/loggedin.asp?display=play"


class LoginTask(Task):
    def __init__(self, email: str, password: str):
        super().__init__(priority=100)
        self.email = email
        self.password = password

    def can_run(self, state: GameState) -> bool:
        return not state.logged_in

    def run(self, state: GameState):
        return Action("login", email=self.email, password=self.password)
