import requests
import argparse
from pocketbase import PocketBase
from Views.globals.app_configs import AppConfigs


def check_pocketbase_server(use_local=False):
    """Check if a PocketBase server is accessible."""

    # Get base URL from app configs or use local if specified
    base_url = "http://127.0.0.1:8090" if use_local else AppConfigs().pb_url

    print(f"Checking PocketBase server at {base_url}...")

    # Try to access the server
    try:
        # Initialize PocketBase client
        client = PocketBase(base_url)

        # Try to get the health check endpoint
        try:
            response = requests.get(f"{base_url}/api/health")
            if response.status_code == 200:
                print("Server is accessible and healthy!")
                return True
        except:
            pass

        # Try to list collections as a fallback
        try:
            collections = client.collections.get_list(1, 1)
            print(
                f"Server is accessible! Found {collections.total_items} collections.")
            return True
        except Exception as e:
            print(f"Error connecting to server: {e}")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False


def print_instructions():
    """Print instructions for setting up PocketBase."""
    print("\nInstructions to set up PocketBase:")
    print("1. Download PocketBase from https://pocketbase.io/")
    print("2. Extract the executable to a directory")
    print("3. Create a data directory (e.g., pb_data)")
    print("4. Run the PocketBase server with: ./pocketbase serve --dir ./pb_data")
    print("5. Access the admin UI at http://127.0.0.1:8090/_/")
    print("6. Create an admin account")
    print("7. Create the necessary collections for your application")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check PocketBase server")
    parser.add_argument("--local", action="store_true",
                        help="Check local PocketBase server instead of remote")

    args = parser.parse_args()

    if not check_pocketbase_server(args.local):
        print("\nCould not connect to the PocketBase server!")
        print_instructions()
    else:
        print("\nPocketBase server is running and accessible.")
