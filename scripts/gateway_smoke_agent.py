"""Fixed, untrusted-side client used only by the disposable B2 smoke probe."""
import json
import os
import sys
import time
from pathlib import Path
import urllib.error
import urllib.request


def main():
    url = os.environ['REPOPILOT_MODEL_GATEWAY_URL']
    credential_file = Path(os.environ['REPOPILOT_MODEL_CREDENTIAL_FILE'])
    credential = credential_file.read_text(encoding='ascii')
    checks = {}
    try:
        with credential_file.open('a') as stream:
            stream.write('should not be writable')
    except OSError:
        checks['credential_mount_readonly'] = True
    else:
        checks['credential_mount_readonly'] = False
    checks['no_database_file'] = not Path('/run/repopilot/database.json').exists()
    checks['no_private_evidence'] = not Path('/evidence').exists()
    checks['no_docker_socket'] = not Path('/var/run/docker.sock').exists()
    body = {'call_id':'smoke-first','messages':[{'role':'user','content':'fixed smoke message; no repository data'}]}

    def call(data, bearer):
        request = urllib.request.Request(url, data=json.dumps(data).encode(),
            headers={'Content-Type':'application/json', 'Authorization':'Bearer '+bearer})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    checks['invalid_credential_rejected'] = call(body, 'invalid')[0] == 401
    if '--concurrent' in sys.argv:
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier=Barrier(8,timeout=8)
        def concurrent(_):
            barrier.wait()
            return call(body,credential)
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies=list(pool.map(concurrent,range(8)))
        checks['concurrent_http_same_id']=all(r[0] in (200,202) for r in replies) and any(r[0]==200 for r in replies)
    first = call(body, credential)
    second = call(body, credential)
    checks['mock_success'] = (first[0] == 200 and first[1].get('transport') == 'mock'
                              and first[1].get('usage') is None)
    checks['duplicate_exact_replay'] = first == second and first[0] == 200
    checks['different_body_conflict'] = call({**body,'messages':[{'role':'user','content':'different'}]},credential)[0] == 409
    checks['unknown_usage_blocks_new_call'] = call({**body,'call_id':'smoke-second'},credential)[0] == 409
    checks['upstream_override_rejected'] = call({**body,'model':'not-frozen'},credential)[0] == 422
    Path('/output/smoke-checks.json').write_text(json.dumps(checks),encoding='utf-8')
    if '--hold' in sys.argv and checks and all(checks.values()):
        Path('/output/ready-for-fault').write_text('ready',encoding='ascii')
        # Fixed acceptance fixture only; production gateway has no delay/fault API.
        time.sleep(90)
    # Deliberately do not echo the bearer, headers, or raw errors.
    return 0 if checks and all(checks.values()) else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(2) from None
