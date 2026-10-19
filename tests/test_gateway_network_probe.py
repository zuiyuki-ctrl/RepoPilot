"""Offline tests for probe orchestration; no Docker/model/database dependencies."""
import json
from unittest.mock import patch
import pytest
from scripts import probe_gateway_network as probe

IMAGE = 'sha256:' + 'a'*64


def record(group='deny', expected=False, observed=False):
    return dict(name='probe', group=group, expected=expected, observed=observed)


def test_negative_control_is_not_proof_of_isolation():
    checks=[record(),record('control',True,False)]
    assert probe.summarize(checks,True)=='inconclusive'
    assert probe.summarize([record(observed=True)],True)=='failed'
    assert probe.summarize([record(observed=True)],True,'later_error')=='failed'
    assert probe.summarize([record()],False)=='cleanup_unconfirmed'
    assert probe.summarize([record()],True,'docker_command_failed')=='inconclusive'
    assert probe.summarize([],True)=='inconclusive'
    assert probe.summarize([record(),record('control',True,True)],True)=='passed'


def test_container_has_no_host_network_secret_mount_or_privileges():
    args=probe.create_args('probe','owner','internal',IMAGE,'idle')
    assert '--pull=never' in args and '--read-only' in args
    assert args[args.index('--network')+1]=='internal'
    assert args[args.index('--user')+1]=='10001:10001'
    assert args[args.index('--cap-drop')+1]=='ALL'
    assert '--privileged' not in args and '--publish' not in args and '--env-file' not in args
    assert args.count('--mount')==1
    assert 'target=/probe.py,readonly' in args[args.index('--mount')+1]
    assert 'docker.sock' not in ' '.join(args)
    assert 'none' == probe.create_args('test','owner','none',IMAGE,'idle')[args.index('--network')+1]


def test_network_must_be_internal_and_isolated_without_fallback():
    p=probe.Probe(IMAGE)
    item=dict(Driver='bridge',Internal=True,EnableIPv6=False,Options=probe.ISOLATED)
    with patch.object(probe,'docker') as docker,patch.object(probe,'inspect_owned',return_value=item):
        p.network('internal',True)
    command=docker.call_args.args
    assert '--internal' in command
    assert 'com.docker.network.bridge.gateway_mode_ipv4=isolated' in command
    with patch.object(probe,'docker') as docker,patch.object(probe,'inspect_owned',return_value={**item,'Internal':False}):
        with pytest.raises(probe.ProbeError,match='mismatch'):p.network('bad',True)
        assert docker.call_count==1  # No fallback ordinary bridge/host network.


def test_cleanup_uses_owned_exact_resources_and_verifies_absence():
    p=probe.Probe(IMAGE);p.resources=[('network','net'),('container','agent')]
    with patch.object(probe,'inspect_owned',side_effect=[{},None,{},None]) as inspect,patch.object(probe,'docker') as docker:
        assert p.cleanup()==[]
    assert docker.call_args_list[0].args==('container','rm','--force','--volumes','agent')
    assert docker.call_args_list[1].args==('network','rm','net')
    assert all(call.args[2]==p.owner for call in inspect.call_args_list)


def test_ownership_mismatch_or_inventory_failure_does_not_delete():
    p=probe.Probe(IMAGE);p.resources=[('container','unowned')]
    with patch.object(probe,'inspect_owned',side_effect=probe.ProbeError('resource_ownership_mismatch')),patch.object(probe,'docker') as docker:
        assert p.cleanup()[0]['name']=='unowned'
        docker.assert_not_called()
    with patch.object(probe,'docker',side_effect=probe.ProbeError('inventory_failed')):
        with pytest.raises(probe.ProbeError):probe.inspect_owned('container','name',p.owner)


def test_inspect_rejects_similar_name_and_wrong_label():
    with patch.object(probe,'docker',return_value='name-other') as docker:
        assert probe.inspect_owned('container','name','owner') is None
        assert docker.call_count==1
    with patch.object(probe,'docker',side_effect=['name',json.dumps([{'Config':{'Labels':{probe.LABEL:'other'}}}])]):
        with pytest.raises(probe.ProbeError,match='ownership'):probe.inspect_owned('container','name','owner')


def test_failure_still_cleans_up_and_does_not_report_pass():
    p=probe.Probe(IMAGE)
    with patch.object(probe,'docker',side_effect=probe.ProbeError('docker_command_failed')),patch.object(p,'cleanup',return_value=[]) as cleanup:
        result=p.run()
    cleanup.assert_called_once()
    assert result['status']=='inconclusive' and result['cleanup_confirmed']


def test_image_must_be_immutable():
    for image in ('python:latest','', 'sha256:bad'):
        with pytest.raises(ValueError):probe.Probe(image)
