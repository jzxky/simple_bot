"""
Central domain configuration. Call set_domain() at bot startup before
any handlers run. All modules import BASE_URL from here.
"""

BASE_URL = "https://mafiamatrix.com"


def set_domain(domain: str):
    global BASE_URL
    BASE_URL = f"https://{domain}"
