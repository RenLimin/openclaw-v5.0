import requests
import os
import subprocess
import sys

PROXY_URL = 'http://127.0.0.1:3000/health'
LAUNCHCTL_PATH = '/bin/launchctl'
LAUNCHD_PLIST = 'ai.openclaw.model-scheduling'

def main():
    try:
        response = requests.get(PROXY_URL, timeout=5)
        if response.status_code == 200:
            print(f'✅ health check passed: {response.json()}')
            return {'fire': False, 'message': 'Health check passed'}
        else:
            msg = f'⚠️ health check failed: status code {response.status_code}'
            print(msg)
            return {'fire': True, 'message': msg}
    except Exception as e:
        msg = f'❌ health check failed: {str(e)}'
        print(msg)
        # 尝试重启
        print('🔄 Attempting to restart via launchd')
        plist_path = os.path.expanduser(f'~/Library/LaunchAgents/{LAUNCHD_PLIST}.plist')
        subprocess.run([LAUNCHCTL_PATH, 'unload', plist_path], capture_output=True)
        subprocess.run([LAUNCHCTL_PATH, 'load', plist_path], capture_output=True)
        return {'fire': True, 'message': f'{msg}, attempted restart'}

if __name__ == "__main__":
    result = main()
    print(result)
