"""UNRUN read-only proposal; exact authenticated child/receipt review required."""
import json,re
from huggingface_hub import HfApi
NAMESPACE='Autismo-Yah'
MAX_RESULTS=100
api=HfApi()
if api.whoami().get('name')!=NAMESPACE:raise RuntimeError('IDENTITY_MISMATCH')
rows=[]
for bucket in api.list_buckets(namespace=NAMESPACE):
 ident=getattr(bucket,'id',None)
 if not isinstance(ident,str) or not re.fullmatch(r'Autismo-Yah/[A-Za-z0-9][A-Za-z0-9._-]{0,95}',ident):raise RuntimeError('BUCKET_IDENTITY_INVALID')
 if ident in rows:raise RuntimeError('DUPLICATE_BUCKET')
 if len(rows)>=MAX_RESULTS:raise RuntimeError('BOUNDED_LIST_INCOMPLETE')
 rows.append(ident)
# Private retained capture only; names must not be reproduced in public artifacts.
print(json.dumps({'status':'LIST_ITERATION_RETURNED','namespace':NAMESPACE,'ids':rows,'count':len(rows),'scope':'returned metadata only; no write permission, durability, ownership beyond namespace, or global census proof'},sort_keys=True))
