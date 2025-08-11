import paramiko
import csv
from io import StringIO

def check_status():
    cred_doc = frappe.get_doc("H2H Settings", "H2H Settings")
    SFTP_HOST = cred_doc.public_ip
    SFTP_PORT = cred_doc.port
    SFTP_PASSWORD = cred_doc.get_password("password")
    SFTP_USERNAME = cred_doc.username

    """Establish SFTP connection and return sftp client"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # <-- disables host key checking
    client.connect(
        hostname=SFTP_HOST,
        port=SFTP_PORT,
        username=SFTP_USERNAME,
        password=SFTP_PASSWORD,
        allow_agent=False,
        look_for_keys=False
    )
    sftp = client.open_sftp()

    # Navigate to /Out
    sftp.chdir("/Out")

    # List CSV files
    for file_attr in sftp.listdir_attr():
        if file_attr.filename.endswith(".csv"):
            print(f"\n=== {file_attr.filename} ===")
            
            # Read file content
            with sftp.open(file_attr.filename) as f:
                csv_content = f.read().decode("utf-8")
                
                # Print CSV as table
                reader = csv.reader(StringIO(csv_content))
                for row in reader:
                    print(row)

    sftp.close()
    transport.close()
