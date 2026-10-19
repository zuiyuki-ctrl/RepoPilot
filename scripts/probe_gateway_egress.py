"""Fixed-provider egress network checkpoint; disposable resources, no key/model/DB.

Uses a fresh locally built relay image and a fake TCP supplier. No real provider
DNS or connection is made. This is not TLS or the full B3b deployment acceptance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import subprocess
from pathlib import Path
import time
from .probe_gateway_network import Probe, ProbeError, docker, inspect_owned, summarize, LABEL, ROOT

FIXTURE=Path(__file__).with_name('gateway_egress_fixture.py').resolve()


class EgressProbe(Probe):
    def node(self,suffix,network,mode,alias=None):
        name=self.prefix+'-'+suffix
        self.resources.append(('container',name))
        source=str(FIXTURE)
        if any(c in source for c in (',','\r','\n')):raise ProbeError('unsafe_mount')
        args=['container','create','--pull=never','--name',name,'--label',f'{LABEL}={self.owner}',
            '--network',network,'--read-only','--user','10001:10001','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--pids-limit','64','--memory','128m','--cpus','0.5',
            '--log-driver','none','--no-healthcheck','--tmpfs','/tmp:rw,noexec,nosuid,size=16m',
            '--mount',f'type=bind,source={source},target=/fixture.py,readonly',
            '--entrypoint','python']
        if alias:args+=['--network-alias',alias]
        docker(*args,self.image,'-I','-B','/fixture.py',mode)
        return name

    def observe(self,name,container,kind,host,port,*,target='',expected=True,group='allow'):
        value=json.loads(docker('exec',container,'python','-I','-B','/fixture.py','check',kind,host,str(port),target))['ok']
        if type(value) is not bool:raise ProbeError('bad_result')
        self.checks.append(dict(name=name,group=group,expected=expected,observed=value))
        print(name+': '+('ok' if value==expected else 'MISMATCH'),flush=True)
        return value

    def run(self):
        report=dict(schema_version=1,probe_id=self.owner,image=self.image,checks=self.checks,
            started_at=datetime.now(timezone.utc).isoformat(),
            scope='Actual Docker TCP isolation and fixed CONNECT policy with fake dialer; no TLS/DB/provider',
            fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            relay_source_sha256=hashlib.sha256((ROOT/'backend/app/services/gateway_egress.py').read_bytes()).hexdigest())
        error=None
        try:
            version=json.loads(docker('version','--format','{{json .Server}}'))
            if version['Os']!='linux' or int(version['Version'].split('.')[0])<28:raise ProbeError('engine_28_required')
            image=json.loads(docker('image','inspect',self.image))[0]
            if image['Id']!=self.image or image['Config'].get('Volumes'):raise ProbeError('image_mismatch_or_volumes')
            agent_net=self.network('agents',True)
            proxy_net=self.network('egress-only',True)
            outside=self.network('fake-provider',False)
            supplier=self.node('supplier',outside,'supplier','fake-supplier')
            proxy=self.node('proxy',outside,'proxy')
            docker('network','connect','--alias','provider-egress',proxy_net,proxy)
            gateway=self.node('gateway',proxy_net,'idle')
            docker('network','connect',agent_net,gateway)
            agent=self.node('agent',agent_net,'idle')
            offline=self.node('offline','none','idle')
            for node in (supplier,proxy,gateway,agent,offline):docker('container','start',node)
            # Ensure source on disk is actually the source in the immutable image.
            source_hash=docker('exec',proxy,'python','-I','-c',
                "import hashlib;print(hashlib.sha256(open('/app/backend/app/services/gateway_egress.py','rb').read()).hexdigest())")
            if source_hash!=report['relay_source_sha256']:raise ProbeError('stale_relay_image')
            for _ in range(20):
                ready=json.loads(docker('exec',proxy,'python','-I','/fixture.py','check','tcp','127.0.0.1','8081',''))['ok']
                if ready:break
                time.sleep(.2)
            else:raise ProbeError('relay_not_ready')
            nodes={n:inspect_owned('container',n,self.owner) for n in (supplier,proxy,gateway,agent,offline)}
            for n,networks in ((agent,{agent_net}),(gateway,{agent_net,proxy_net}),(proxy,{outside,proxy_net}),(offline,{'none'})):
                if (set(nodes[n]['NetworkSettings']['Networks'])!=networks or nodes[n]['HostConfig']['PortBindings']
                        or nodes[n]['HostConfig']['Privileged']):raise ProbeError('topology_differs')
            supplier_ip=nodes[supplier]['NetworkSettings']['Networks'][outside]['IPAddress']
            proxy_ip=nodes[proxy]['NetworkSettings']['Networks'][proxy_net]['IPAddress']
            for port in (443,8000,5432):
                self.observe(f'positive_supplier_{port}',proxy,'tcp',supplier_ip,port,group='control')
                self.observe(f'gateway_cannot_bypass_{port}',gateway,'tcp',supplier_ip,port,expected=False,group='deny')
                self.observe(f'agent_cannot_reach_supplier_{port}',agent,'tcp',supplier_ip,port,expected=False,group='deny')
            self.observe('gateway_fixed_tunnel',gateway,'tunnel','provider-egress',8081,target='dashscope.aliyuncs.com:443')
            for i,target in enumerate(('example.com:443','host.docker.internal:8000','127.0.0.1:443',
                                      supplier_ip+':443','dashscope.aliyuncs.com:80')):
                self.observe('relay_rejects_target_'+str(i),gateway,'tunnel','provider-egress',8081,target=target)
            self.observe('agent_cannot_reach_relay',agent,'tcp',proxy_ip,8081,expected=False,group='deny')
            self.observe('test_stays_offline',offline,'tcp',proxy_ip,8081,expected=False,group='deny')
        except (ProbeError,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
            error=str(exc) if isinstance(exc,ProbeError) else type(exc).__name__
        finally:
            errors=self.cleanup()
            report.update(error_code=error,cleanup_confirmed=not errors,cleanup_errors=errors,
                          completed_at=datetime.now(timezone.utc).isoformat())
            report['status']=summarize(self.checks,not errors,error)
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:parser.error('--execute required')
    probe=EgressProbe(args.image)
    report=probe.run()
    directory=ROOT/'.platform-artifacts'/'gateway-egress';directory.mkdir(parents=True,exist_ok=True)
    path=directory/(probe.owner+'.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'Status: {report["status"]}; cleanup_confirmed={report["cleanup_confirmed"]}\nReport: {path}')
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
