"""Guard the no-call acceptance mode without starting Docker or touching secrets."""
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import uuid4

import pytest
from scripts import probe_gateway_runtime as probe
from backend.app.services import gateway_runtime as runtime


@pytest.mark.parametrize('kwargs', [dict(live_no_call=True), dict(egress_image='sha256:'+'a'*64),
    dict(live_no_call=True,egress_image='sha256:'+'a'*64,tls_fixture=True),dict(tls_fixture=True,faults=True)])
def test_incompatible_probe_modes_fail_before_resources(kwargs):
    with pytest.raises(ValueError):probe.run_probe('unused','unused','unused',**kwargs)


def topology():
    rid,token=uuid4(),uuid4()
    names=runtime.names(rid,token)
    def node(nets,mounts):
        return dict(NetworkSettings={'Networks':dict.fromkeys(nets,{})},HostConfig={'PortBindings':{},'Privileged':False},Mounts=mounts)
    nodes={names['agent']:node([names['network']],[]),
        names['gateway']:node(['control',names['network'],names['proxy-network']],
            [{'Destination':'/run/repopilot/provider-key','RW':False}]),
        names['proxy']:node([names['proxy-network'],names['egress-network']],[])}
    stub=NS(names=runtime.names,inspect_owned=lambda kind,name,*_:nodes[name],
        docker=Mock(return_value=NS(returncode=0)))
    return rid,token,names,nodes,stub


def test_probe_checks_real_topology_and_only_denied_connect():
    rid,token,names,nodes,stub=topology();checks={}
    probe.inspect_live_topology(stub,rid,token,'control',checks)
    assert all(checks.values()) and len(checks)==5
    command=stub.docker.call_args.args[-1]
    assert 'example.invalid:443' in command and 'dashscope.aliyuncs.com' not in command


@pytest.mark.parametrize('change',['extra_network','secret_to_agent','writable_key','proxy_mount','proxy_rejection_failed'])
def test_probe_does_not_pass_bad_deployment(change):
    rid,token,names,nodes,stub=topology();checks={}
    if change=='extra_network':nodes[names['agent']]['NetworkSettings']['Networks'][names['egress-network']]={}
    if change=='secret_to_agent':nodes[names['agent']]['Mounts']=[{'Destination':'/run/repopilot/provider-key'}]
    if change=='writable_key':nodes[names['gateway']]['Mounts'][0]['RW']=True
    if change=='proxy_mount':nodes[names['proxy']]['Mounts']=[{'Destination':'/secret'}]
    if change=='proxy_rejection_failed':stub.docker.return_value=NS(returncode=1)
    with pytest.raises(RuntimeError):probe.inspect_live_topology(stub,rid,token,'control',checks)
    assert not all(checks.values())
