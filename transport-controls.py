"""UNRUN synthetic transport controls: temporary data only, no network/GAME."""
import contextlib,hashlib,importlib.util,io,json,pathlib,sys,tempfile
HERE=pathlib.Path(__file__).resolve().parent

def load(file,name):
 spec=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def sha(b):return hashlib.sha256(b).hexdigest()

def main():
 frame=load('output-frames.py','synthetic_frame');reassemble=load('reassemble-output.py','synthetic_reassemble');extract=load('extract-output.py','synthetic_extract')
 with tempfile.TemporaryDirectory(prefix='slug-transport-control-') as tmp:
  root=pathlib.Path(tmp);frame.ROOT=root;frame.ONE=root/'one';frame.ONE.mkdir();manifest={}
  for n in frame.FILES:
   p=frame.ONE/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('synthetic '+n).encode());manifest[n]={'bytes':p.stat().st_size,'sha256':sha(p.read_bytes()),'mode':'100644'}
  shard=frame.ONE/'docs/dialogues/0123456789abcdef.json';shard.parent.mkdir(parents=True,exist_ok=True);shard.write_text('{"synthetic":true}\n');manifest[shard.relative_to(frame.ONE).as_posix()]={'bytes':shard.stat().st_size,'sha256':sha(shard.read_bytes()),'mode':'100644'}
  for n in ('before','first','second'):(root/(n+'-data-docs-manifest.json')).write_text(json.dumps(manifest,sort_keys=True))
  (root/'comparison.json').write_text(json.dumps({'source':'428591a413a55973e2fde1f7c479d34e64057edf','dataDocsFiles':len(manifest),'changed':{},'dataDocsEqual':True,'nonOutputSourceEqual':True}))
  labels=('install','dependency-check','regression','export-one','export-two');commands={}
  for label in labels:
   commands[label]=['synthetic',label];record={'label':label,'argv':commands[label],'status':'COMPLETE','exit':0,'timedOut':False,'processGroupGone':True,'unexpectedLeftoverGroup':False,'forcedCleanup':False,'signal':None,'errors':[]}
   for stream in ('stdout','stderr'):
    data=('synthetic '+label+' '+stream).encode();(root/(label+'.'+stream)).write_bytes(data);record[stream]={'bytes':len(data),'sha256':sha(data)}
   (root/(label+'.result.json')).write_text(json.dumps(record))
  commands['frame']=['synthetic','frame']
  def wrap(text):
   data=text.encode();record={'label':'frame','argv':commands['frame'],'status':'COMPLETE','exit':0,'timedOut':False,'processGroupGone':True,'unexpectedLeftoverGroup':False,'forcedCleanup':False,'signal':None,'errors':[],'stdout':{'bytes':len(data),'sha256':sha(data)},'stderr':{'bytes':0,'sha256':sha(b'')}}
   return json.dumps({'event':'command-result','result':record})+'\n'+text+json.dumps({'event':'frame-relay-complete','bytes':len(data),'sha256':sha(data)})+'\n'
  buf=io.StringIO()
  with contextlib.redirect_stdout(buf):frame.main()
  lines=buf.getvalue().splitlines(keepends=True);raw=root/'raw.log';raw.write_text(wrap(''.join(lines)));cmd=root/'commands.json';cmd.write_text(json.dumps(commands,sort_keys=True));cmdsha=sha(cmd.read_bytes())
  def restore(rawfile,out,expect):
   old=sys.argv;sys.argv=['reassemble-output.py',str(rawfile),str(out),str(cmd),cmdsha]
   try:
    try:reassemble.main()
    except Exception:
     if expect:raise
    else:
     if not expect:raise AssertionError('malformed stream accepted')
   finally:sys.argv=old
  restore(raw,root/'valid',True)
  receipt=root/'valid/reassembly.json';archive=root/'valid/qualified-output.tar.gz';old=sys.argv
  sys.argv=['extract-output.py',str(archive),sha(archive.read_bytes()),str(receipt),sha(receipt.read_bytes()),str(root/'extracted')]
  try:extract.main()
  finally:sys.argv=old
  assert (root/'extracted/docs/dialogues/0123456789abcdef.json').read_bytes()==shard.read_bytes()
  for label,bad in [('partial',lines[:-1]),('duplicate',lines[:2]+[lines[1]]+lines[2:]),('unknown',lines[:1]+['{"event":"slug-output-unexpected","version":1}\n']+lines[1:])]:
   path=root/(label+'.log');path.write_text(wrap(''.join(bad)));restore(path,root/label,False)
  old_commands=cmd.read_bytes();commands['regression']=['synthetic','wrong'];cmd.write_text(json.dumps(commands,sort_keys=True));cmdsha=sha(cmd.read_bytes());restore(raw,root/'argv-mismatch',False);cmd.write_bytes(old_commands);cmdsha=sha(old_commands)
  def extract_fails(archive_path,archive_sha,receipt_path,receipt_sha,out):
   old=sys.argv;sys.argv=['extract-output.py',str(archive_path),archive_sha,str(receipt_path),receipt_sha,str(out)]
   try:
    try:extract.main()
    except Exception:pass
    else:raise AssertionError('invalid extraction accepted')
   finally:sys.argv=old
  tampered=root/'tampered.tar.gz';data=bytearray(archive.read_bytes());data[-1]^=1;tampered.write_bytes(data)
  extract_fails(tampered,sha(archive.read_bytes()),receipt,sha(receipt.read_bytes()),root/'tampered-output')
  extract_fails(archive,sha(archive.read_bytes()),receipt,'0'*64,root/'tampered-receipt')
  extract_fails(archive,sha(archive.read_bytes()),receipt,sha(receipt.read_bytes()),root/'extracted')
  badindex=list(lines);row=json.loads(badindex[1]);row['index']=999999;badindex[1]=json.dumps(row)+'\n';path=root/'bad-index.log';path.write_text(wrap(''.join(badindex)));restore(path,root/'bad-index',False)
  path=root/'duplicate-json.log';path.write_text(wrap(lines[0]+'{"event":"slug-output-chunk","event":"duplicate"}\n'+''.join(lines[1:])));restore(path,root/'duplicate-json',False)
  path=root/'oversized-line.log';path.write_bytes(b'x'*(reassemble.MAX_LINE+1)+b'\n');restore(path,root/'oversized-line',False)
  # Reframe synthetic evidence after forcing an invalid command outcome.
  result_path=root/'regression.result.json';good_result=result_path.read_bytes();bad_result=json.loads(good_result);bad_result['forcedCleanup']=True;result_path.write_text(json.dumps(bad_result));(root/'qualified-output.tar.gz').unlink()
  buf=io.StringIO()
  with contextlib.redirect_stdout(buf):frame.main()
  path=root/'forced-cleanup.log';path.write_text(wrap(buf.getvalue()));restore(path,root/'forced-cleanup',False);result_path.write_bytes(good_result)
  # A divergent second manifest must not be accepted as reproducible output.
  second=root/'second-data-docs-manifest.json';good_second=second.read_bytes();second.write_text('{}');(root/'qualified-output.tar.gz').unlink()
  buf=io.StringIO()
  with contextlib.redirect_stdout(buf):frame.main()
  path=root/'changed-map.log';path.write_text(wrap(buf.getvalue()));restore(path,root/'changed-map',False);second.write_bytes(good_second)
  # Sealed input corruption must be refused by the emitter before framing.
  original=shard.read_bytes();shard.write_bytes(b'corrupt');(root/'qualified-output.tar.gz').unlink()
  try:
   with contextlib.redirect_stdout(io.StringIO()):frame.main()
  except Exception:pass
  else:raise AssertionError('corrupt sealed output accepted')
  shard.write_bytes(original)
  # Simulated fsync failure must not report successful extraction.
  original_fsync=extract.os.fsync;extract.os.fsync=lambda fd: (_ for _ in ()).throw(OSError('synthetic fsync failure'))
  try:extract_fails(archive,sha(archive.read_bytes()),receipt,sha(receipt.read_bytes()),root/'fsync-failure')
  finally:extract.os.fsync=original_fsync
  (root/'qualified-output.tar.gz').unlink(missing_ok=True)
  frame.MAX_ARCHIVE=1
  try:
   with contextlib.redirect_stdout(io.StringIO()):frame.main()
  except RuntimeError:pass
  else:raise AssertionError('compressed size cap accepted')
 print('PASS: synthetic roundtrip, frame/bounds, argv/cleanup, manifest/output tamper, extraction collision/fsync and compressed cap')
if __name__=='__main__':main()
