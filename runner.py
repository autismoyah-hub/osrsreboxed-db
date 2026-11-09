"""UNREVIEWED SOURCE DRAFT. Do not submit or execute.

No credentials, provider access, cache, server or gameplay are involved here.
Caller must bind this file, plan, exact wheel manifest, source and image.
"""
import base64, hashlib, json, os, pathlib, shutil, subprocess, sys, tarfile, tempfile, urllib.request

ROOT = pathlib.Path('/tmp/slug-export-qualification')
SOURCE = 'https://codeload.github.com/autismoyah-hub/osrsreboxed-db/tar.gz/428591a413a55973e2fde1f7c479d34e64057edf'
SOURCE_SHA = '7e43b7bc403e0942549ecfa8a6fc36f3ebe2ee67a10c233ab8cab44ccfd1f51b'
SOURCE_BYTES = 104209168
WHEELS_SHA = '3507cb7213863d82ae3a36f3324917f58a10f770f1fafa53a0ea19660fa2440d'
WIKI_SHA = 'df1d3a498eccc175f17a3a3aa0080c4123320cd21a4e4c8998911856d75238b8'
OUT_FILES = {'docs/npc-dialogues.json','docs/npc-dialogues-minified.json','docs/event-dialogues.json','docs/npc-dialogue-index.json','docs/dialogue-types.json','docs/dialogue-manifest.json','data/dialogues/inferred-actions.txt','data/dialogues/authoring-index.json','data/dialogues/review-issues.json'}

def digest_file(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while True:
   b=f.read(1048576)
   if not b: return h.hexdigest()
   h.update(b)

def fetch(url, target, size, sha):
 h=hashlib.sha256(); count=0
 with urllib.request.urlopen(url, timeout=120) as response, target.open('xb') as f:
  while True:
   b=response.read(1048576)
   if not b: break
   count+=len(b)
   if count>size: raise RuntimeError('download exceeds pinned length')
   h.update(b); f.write(b)
 if count!=size or h.hexdigest()!=sha: raise RuntimeError('download identity mismatch')

def snapshot(root, exclude_outputs=False):
 result={}
 for path in sorted(root.rglob('*')):
  if path.is_symlink(): raise RuntimeError('symlink in tree')
  if not path.is_file(): continue
  rel=path.relative_to(root).as_posix()
  if exclude_outputs and (rel in OUT_FILES or rel.startswith('docs/dialogues/')): continue
  result[rel]={'bytes':path.stat().st_size,'sha256':digest_file(path)}
 return result

def run(label, cmd, cwd, env):
 result=subprocess.run(cmd,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1800,check=False)
 (ROOT/(label+'.stdout')).write_bytes(result.stdout); (ROOT/(label+'.stderr')).write_bytes(result.stderr)
 print(json.dumps({'event':'command','label':label,'argv':cmd,'exit':result.returncode,'stdoutSHA256':hashlib.sha256(result.stdout).hexdigest(),'stderrSHA256':hashlib.sha256(result.stderr).hexdigest()}),flush=True)
 if result.returncode: raise RuntimeError(label+' failed')

def main():
 if sys.version_info[:2]!=(3,9) or sys.platform!='linux': raise RuntimeError('requires reviewed Python 3.9 Linux image')
 ROOT.mkdir(mode=0o700)
 wheels_raw=pathlib.Path('/case/wheels.json').read_bytes()
 if hashlib.sha256(wheels_raw).hexdigest()!=WHEELS_SHA: raise RuntimeError('wheel manifest mismatch')
 wheels=json.loads(wheels_raw); wheel_dir=ROOT/'wheels';wheel_dir.mkdir()
 for w in wheels: fetch(w['url'],wheel_dir/w['filename'],w['bytes'],w['sha256'])
 source_archive=ROOT/'source.tar.gz';fetch(SOURCE,source_archive,SOURCE_BYTES,SOURCE_SHA)
 base=ROOT/'base';base.mkdir()
 with tarfile.open(source_archive,'r:gz') as t:
  members=t.getmembers(); prefix='osrsreboxed-db-428591a413a55973e2fde1f7c479d34e64057edf/'
  seen=set()
  for m in members:
   if m.name == prefix.rstrip('/') and m.isdir(): continue
   if not m.name.startswith(prefix) or m.name in seen or any(x in ('.','..','') for x in m.name[len(prefix):].rstrip('/').split('/')) or not (m.isdir() or m.isfile()): raise RuntimeError('unexpected archive entry')
   seen.add(m.name)
  t.extractall(base,members=members)
 extracted=base/prefix.rstrip('/'); source=json.loads((extracted/'data/dialogues/quest-pages.json').read_text())['Transcript:The Slug Menace']
 if source['revision']!=15395854 or hashlib.sha256(source['wikitext'].encode()).hexdigest()!=WIKI_SHA: raise RuntimeError('wiki pin mismatch')
 deps=ROOT/'deps';deps.mkdir();env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_NO_INDEX='1')
 run('install',[sys.executable,'-m','pip','install','--no-index','--no-deps','--target',str(deps)]+[str(wheel_dir/w['filename']) for w in wheels],ROOT,env)
 env['PYTHONPATH']=str(deps)
 one=ROOT/'one';two=ROOT/'two';shutil.copytree(extracted,one);shutil.copytree(extracted,two)
 # Seal each copy before tests/export; outputs can change only at declared paths.
 initial_one=snapshot(one,True);initial_two=snapshot(two,True)
 if initial_one!=initial_two: raise RuntimeError('initial source copies differ')
 before_data_docs={k:v for k,v in snapshot(extracted).items() if k.startswith(('data/','docs/'))}
 run('regression',[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','test/test_dialogue_refresh_revision.py'],one,env)
 for name,tree in [('one',one),('two',two)]:run('export-'+name,[sys.executable,'-m','scripts.dialogues.update','--offline'],tree,env)
 if snapshot(one,True)!=initial_one or snapshot(two,True)!=initial_two: raise RuntimeError('non-output source changed')
 first={k:v for k,v in snapshot(one).items() if k.startswith(('data/','docs/'))};second={k:v for k,v in snapshot(two).items() if k.startswith(('data/','docs/'))}
 if first!=second: raise RuntimeError('full data/docs path or hash differs')
 report={'event':'export-comparison','source':'428591a413a55973e2fde1f7c479d34e64057edf','dataDocsFiles':len(first),'changed':{k:{'before':before_data_docs.get(k),'after':first.get(k)} for k in sorted(before_data_docs.keys()|first.keys()) if before_data_docs.get(k)!=first.get(k)},'dataDocsEqual':True,'nonOutputSourceEqual':True}
 (ROOT/'comparison.json').write_text(json.dumps(report,sort_keys=True)+'\n')
 print(json.dumps({'event':'comparison-summary','changedFiles':len(report['changed']),'comparisonSHA256':digest_file(ROOT/'comparison.json')}),flush=True)
 # Output retention intentionally unresolved. No claim of complete collected output.
 raise RuntimeError('OUTPUT_RETENTION_NOT_REVIEWED')

if __name__=='__main__':main()
