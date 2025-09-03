# backend_app/otp_utils.py
import random

def generate_otp():
    return str(random.randint(100000, 999999))
