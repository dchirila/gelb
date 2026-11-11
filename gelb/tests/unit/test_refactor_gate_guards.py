"""Fail-closed skip evidence, independent allowances, and candidate syntax."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


value = module('differential_value_gate')
emission = module('emission_snapshot')
SHA = 'a' * 64


def manifest():
    return dict(format=1, settings={'configs': ['soa']}, compiler_versions={}, highway_revision='revision',
                headers=dict.fromkeys(value.HEADERS, SHA), runners=dict.fromkeys(value.RUNNERS, SHA),
                inputs={'example.gelb': {'sha256': SHA, 'random': False}},
                runs={'example.gelb': {'soa': dict(status=0, variables={'v': SHA}, source_sha256=SHA)}})


def save(directory, data):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'manifest.json').write_text(json.dumps(data))
    return directory


@pytest.mark.parametrize('bad', [None, '', 'invalid', '0' * 63])
def test_missing_or_invalid_hash_names_entry(bad):
    data = manifest()
    entry = data['runs']['example.gelb']['soa']
    if bad is None:
        del entry['source_sha256']
    else:
        entry['source_sha256'] = bad
    with pytest.raises(ValueError, match=r'example.gelb \(soa\)'):
        value.require_hashes(data, ['soa'])


def prepared(monkeypatch, tmp_path, data):
    path = tmp_path / 'example.gelb'
    path.write_text('fixture')
    data = copy.deepcopy(data)
    data['runs'] = {}
    monkeypatch.setattr(value, 'prepare_record', lambda args:
        (tmp_path, args.out, tmp_path, [path], ['soa'], {}, copy.deepcopy(data)))
    monkeypatch.setattr(value, 'generated_hash', lambda *args: SHA)


@pytest.mark.parametrize('mutation', ['control', 'hash', 'removed', 'runners', 'settings', 'inputs', 'headers', 'highway_revision', 'compiler_versions'])
def test_verify_source_guard(tmp_path, monkeypatch, mutation):
    before, after = manifest(), manifest()
    prepared(monkeypatch, tmp_path, after)
    if mutation == 'hash':
        before['runs']['example.gelb']['soa']['source_sha256'] = 'b' * 64
    elif mutation == 'removed':
        del before['runs']['example.gelb']['soa']['source_sha256']
    elif mutation == 'runners':
        del before['runners']
    elif mutation == 'highway_revision':
        before[mutation] = 'changed'
    elif mutation != 'control':
        before[mutation]['changed'] = 'changed'
    args = NS(baseline=save(tmp_path / 'baseline', before), configs='soa', strict_fp=False,
              steps=3, jobs=1, timeout=30)
    if mutation == 'control':
        assert value.verify_sources(args) == 0
    else:
        with pytest.raises(ValueError):
            value.verify_sources(args)


def test_backward_compatible_values_and_separate_exceptions(tmp_path):
    before, after = manifest(), manifest()
    del before['runners']
    del before['runs']['example.gelb']['soa']['source_sha256']
    args = NS(baseline=save(tmp_path / 'baseline', before), candidate=save(tmp_path / 'candidate', after),
              allow_changed='', allow_changed_headers='')
    assert value.compare_baseline(args) == 0
    after['runs']['example.gelb']['soa']['variables']['v'] = 'changed'
    save(args.candidate, after)
    assert value.compare_baseline(args) == 1
    args.allow_changed = 'example.gelb'
    assert value.compare_baseline(args) == 0


@pytest.mark.parametrize('name', value.HEADERS + value.RUNNERS)
def test_changed_dependencies_and_header_exceptions(tmp_path, monkeypatch, name):
    for path in (*value.HEADERS, *value.RUNNERS):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'base')
    monkeypatch.setattr(value.subprocess, 'check_output', lambda *a, **k: b'base')
    (tmp_path / name).write_bytes(b'changed')
    args = NS(tree=tmp_path, base='base', command='check-runners', allow_changed_headers='')
    with pytest.raises(ValueError, match='changed dependency'):
        value.check_base_files(args)
    if name in value.HEADERS:
        args.command = 'check-headers'
        with pytest.raises(ValueError):
            value.check_base_files(args)
        args.allow_changed_headers = name
        assert value.check_base_files(args) == 0
        args.command = 'check-runners'
        with pytest.raises(ValueError, match='cannot be combined'):
            value.check_base_files(args)


def test_header_allowlist_is_exact_and_retains_other_guards():
    for invalid in ('*', 'gelb/backends', value.RUNNERS[0]):
        with pytest.raises(ValueError):
            value.allowed_headers(invalid)
    before, after = manifest(), manifest()
    header = value.HEADERS[0]
    after['headers'][header] = 'changed'
    value.compatible(before, after, {header})
    with pytest.raises(ValueError):
        value.compatible(before, after, {value.HEADERS[1]})
    for key in ('settings', 'inputs', 'runners', 'compiler_versions'):
        changed = copy.deepcopy(after)
        changed[key]['unexpected'] = 'changed'
        with pytest.raises(ValueError):
            value.compatible(before, changed, {header}, sources=True)


@pytest.mark.parametrize('kind', ['smoke', 'plain-build'])
@pytest.mark.parametrize('mutation', ['control', 'hash', 'removed', 'iterations', 'backends'])
def test_build_hash_roundtrip_settings_and_mutants(tmp_path, monkeypatch, kind, mutation):
    prepared(monkeypatch, tmp_path, manifest())
    args = NS(backends='serial,cpu_highway', build_hashes=tmp_path / 'hashes', kind=kind,
              command='record-build-hashes', smoke_iters=10, jobs=1, timeout=30)
    assert value.build_hashes(args) == 0
    args.command = 'verify-build-hashes'
    target = args.build_hashes / kind
    data = json.loads((target / 'manifest.json').read_text())
    if mutation == 'iterations':
        if kind == 'smoke':
            args.smoke_iters = 11
        else:
            data['settings']['steps'] = 2
    elif mutation == 'backends':
        args.backends = 'serial'
    elif mutation == 'hash':
        data['runs']['example.gelb']['cpu_highway']['source_sha256'] = 'b' * 64
    elif mutation == 'removed':
        del data['runs']['example.gelb']['cpu_highway']['source_sha256']
    save(target, data)
    if mutation == 'control':
        assert value.build_hashes(args) == 0
    else:
        with pytest.raises(ValueError):
            value.build_hashes(args)


@pytest.mark.parametrize('path', ['gelb/compiler_pipeline.py', 'gelb/new_pass.py', 'gelb/scripts/gelb-run',
    'scripts/gelb-run', 'third_party/highway', 'pyproject.toml', 'uv.lock',
    'gelb/tests/integration/test_reproducibility.py', 'gelb/tests/integration/conftest.py',
    'gelb/tests/integration/_toolchain.py'])
def test_reproducibility_triggers(path):
    assert value.needs_reproducibility([path])


def test_reproducibility_skip_and_intent_to_add(tmp_path):
    assert not value.needs_reproducibility(['docs/dev/06_testing.rst', 'gelb/tests/unit/test_types.py'])
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / 'base').touch()
    subprocess.run(['git', 'add', 'base'], cwd=tmp_path, check=True)
    subprocess.run(['git', '-c', 'user.name=Tester', '-c', 'user.email=test@example.invalid',
                    '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], cwd=tmp_path, check=True)
    path = tmp_path / 'gelb/new_pass.py'
    path.parent.mkdir()
    path.touch()
    subprocess.run(['git', 'add', '-N', 'gelb/new_pass.py'], cwd=tmp_path, check=True)
    assert value.needs_reproducibility(value.changed_files(tmp_path, 'HEAD'))


def test_structural_emission_and_candidate_syntax(tmp_path):
    base, candidate = tmp_path / 'base', tmp_path / 'candidate'
    text = 'void f() { double g__gelb_cse_0 = 1.; double y = g__gelb_cse_0; }'
    for directory in (base, candidate):
        directory.mkdir()
        (directory / 'sample.cpp').write_text(text)
        (directory / 'MANIFEST.json').write_text(json.dumps(dict(examples=1, emissions=1, failures={})))
    assert emission.compare_directories(base, candidate, mode='structural') == 0
    path = candidate / 'sample.cpp'
    (base / 'sample.cpp').write_bytes((text + '\n').encode())
    path.write_bytes((text + '\r\n').encode())
    assert emission.compare_directories(base, candidate, mode='byte') == 1
    (base / 'sample.cpp').write_text(text)
    path.write_text(text.replace('cse_0', 'cse_9'))
    assert emission.compare_directories(base, candidate, mode='structural') == 0
    path.write_text(text.replace('= g__gelb_cse_0', '= g__gelb_cse_9'))
    assert emission.compare_directories(base, candidate, mode='structural') == 1
    path.write_text(text)
    assert emission.syntax(candidate, 1) == 0
    path.write_text('this is a syntax error;')
    assert emission.syntax(candidate, 1) == 1
    assert (base / 'sample.cpp').read_text() == text


# A command stub isolates shell orchestration; the helpers above exercise the
# actual guard logic, and integration runs exercise the real compiler drivers.
STUB = '''import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['COMMAND_LOG'], 'a') as f: f.write(json.dumps(args) + '\\n')
if len(args) > 3 and args[2] == '-':
    if len(args) == 7: pathlib.Path(args[-1]).write_text('fortran,soa,aos,cbt,cuda')
    sys.exit(0)
if args == ['run', 'python', '-']:
    print('\\n'.join('gelb/tests/integration/test_%s.py' % i for i in range(49)))
if 'reproducibility-needed' in args: print(os.environ.get('REPRO', 'RUN'))
if os.environ.get('FAIL_COMMAND', 'unused') in args: sys.exit(1)
'''


@pytest.mark.parametrize('skip,stage', [('--skip-values', 'values-default'), ('--skip-smoke', 'smoke'),
                                      ('--skip-plain-build', 'plain-build')])
@pytest.mark.parametrize('fail', [False, True])
def test_shell_skip_verdicts_and_independent_routing(tmp_path, skip, stage, fail):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    uv = bin_dir / 'uv'
    uv.write_text('#!' + sys.executable + '\n' + STUB)
    uv.chmod(0o755)
    snapshots = tmp_path / 'snapshots'
    for variant in emission.VARIANTS:
        (snapshots / variant).mkdir(parents=True)
    out, commands = tmp_path / 'out', tmp_path / 'commands.jsonl'
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'], COMMAND_LOG=str(commands),
               FAIL_COMMAND='check-runners' if fail else 'unused', REPRO='RUN' if fail else 'SKIP')
    result = subprocess.run(['bash', str(ROOT / 'scripts/run_refactor_gate.sh'), '--tree', str(ROOT),
        '--base', 'HEAD', '--snapshots', str(snapshots), '--baseline-values', str(snapshots),
        '--out', str(out), skip, '--allow-emission-changed', 'emission.gelb',
        '--allow-value-changed', 'value.gelb', '--emission-mode', 'structural'], env=env, capture_output=True, text=True)
    results = (out / 'results.txt').read_text()
    assert result.returncode == int(fail), result.stderr
    assert f'{stage}: {"FAIL" if fail else "SKIP"}\n' in results
    assert f'{stage}: PASS' not in results.splitlines()
    calls = [json.loads(line) for line in commands.read_text().splitlines()]
    if fail:
        assert results == f'{stage}: FAIL\n'
        assert not any('record' in c or 'pytest' in c for c in calls)
    else:
        assert 'reproducibility: SKIP\n' in results
        for call in calls:
            if 'compare-baseline' in call:
                assert 'value.gelb' in call and 'emission.gelb' not in call
            if 'syntax' in call:
                assert str(out / 'emissions') in call[call.index('-o') + 1]
        assert 'integration-ci49:' in (out / 'timings.txt').read_text()


def shell_fixture(tmp_path, *, layout='', extra=(), stub=STUB, env_extra=None):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    uv = bin_dir / 'uv'
    uv.write_text('#!' + sys.executable + '\n' + stub)
    uv.chmod(0o755)
    snapshots = tmp_path / 'snapshots'
    for variant in emission.VARIANTS:
        (snapshots / (layout + variant)).mkdir(parents=True)
    out, commands = tmp_path / 'out', tmp_path / 'commands.jsonl'
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'], COMMAND_LOG=str(commands))
    env.pop('GIT_CEILING_DIRECTORIES', None)
    env.update(env_extra or {})
    result = subprocess.run(['bash', str(ROOT / 'scripts/run_refactor_gate.sh'), '--tree', str(ROOT),
        '--base', 'HEAD', '--snapshots', str(snapshots), '--baseline-values', str(snapshots),
        '--out', str(out), *extra], env=env, capture_output=True, text=True)
    calls = [json.loads(line) for line in commands.read_text().splitlines()]
    return result, out, calls


@pytest.mark.parametrize('layout', ['', 'emis_', 'emis_b5_'])
def test_shell_snapshot_directory_layouts(tmp_path, layout):
    result, _, calls = shell_fixture(tmp_path, layout=layout)
    assert result.returncode == 0, result.stderr
    comparisons = [call for call in calls if 'compare' in call]
    assert len(comparisons) == len(emission.VARIANTS)
    for call in comparisons:
        variant = call[call.index('--variant') + 1]
        assert call[call.index('-o') + 1] == str(tmp_path / 'snapshots' / (layout + variant))


def test_shell_fuzz_baseline_forwards_only_header_allowance(tmp_path):
    corpus = tmp_path / 'fuzz'
    corpus.mkdir()
    result, out, calls = shell_fixture(tmp_path, extra=(
        '--fuzz-dir', str(corpus), '--fuzz-baseline', str(corpus),
        '--allow-changed-headers', value.HEADERS[0], '--allow-value-changed', 'example.gelb'))
    assert result.returncode == 0, result.stderr
    comparisons = [call for call in calls if 'compare-baseline' in call]
    assert len(comparisons) == 4
    for call in comparisons:
        assert call[call.index('--allow-changed-headers') + 1] == value.HEADERS[0]
        if str(out / 'fuzz') in call[call.index('--candidate') + 1]:
            assert '--allow-changed' not in call


def test_shell_out_inside_long_git_path_keeps_temporary_tests_outside_git(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / 'base').touch()
    subprocess.run(['git', 'add', 'base'], cwd=tmp_path, check=True)
    subprocess.run(['git', '-c', 'user.name=Tester', '-c', 'user.email=test@example.invalid',
                    '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], cwd=tmp_path, check=True)
    nested = tmp_path / ('long-' + 'x' * 120)
    nested.mkdir()
    stub = STUB + '''
if args[:2] == ['run', 'pytest']:
    assert len(os.environ['TMPDIR']) < 50, os.environ['TMPDIR']
    if args[-1].endswith('/unit'):
        import subprocess
        code = subprocess.call([sys.executable, '-m', 'pytest', '-q',
            'gelb/tests/unit/test_bench_common.py::test_commit_sha_falls_back_outside_git_repo',
            '--basetemp', args[args.index('--basetemp') + 1]])
        sys.exit(code)
'''
    result, _, _ = shell_fixture(nested, stub=stub, env_extra={'TMPDIR': str(nested)})
    assert result.returncode == 0, result.stderr
