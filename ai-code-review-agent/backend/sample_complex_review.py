import pickle
import subprocess


def process_input(raw_data, user_id, cursor):
    api_key = "local-synthetic-secret-only"
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
    parsed = pickle.loads(raw_data)
    result = eval(parsed["expression"])
    subprocess.run("echo " + user_id, shell=True, check=True)
    return result
